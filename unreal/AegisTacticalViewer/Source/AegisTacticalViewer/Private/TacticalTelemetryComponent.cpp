#include "TacticalTelemetryComponent.h"

#include "AegisTacticalCameraActor.h"
#include "AegisTacticalEffectsManager.h"
#include "AegisTacticalSiteActor.h"
#include "AegisTacticalViewer.h"
#include "Common/UdpSocketBuilder.h"
#include "Containers/StringConv.h"
#include "Dom/JsonObject.h"
#include "Interfaces/IPv4/IPv4Address.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/StaticMeshComponent.h"
#include "EngineUtils.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SocketSubsystem.h"

namespace
{
bool ReadFiniteNumber(const TSharedPtr<FJsonObject>& Object, const FString& Name, double& Out)
{
    return Object.IsValid() && Object->HasTypedField<EJson::Number>(Name)
        && Object->TryGetNumberField(Name, Out) && FMath::IsFinite(Out);
}

bool ReadRequiredString(const TSharedPtr<FJsonObject>& Object, const FString& Name, FString& Out)
{
    return Object.IsValid() && Object->TryGetStringField(Name, Out) && !Out.IsEmpty();
}

bool ReadVector(const TSharedPtr<FJsonObject>& Object, const FString& Name, FVector& Out)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (!Object.IsValid() || !Object->TryGetArrayField(Name, Values)
        || Values == nullptr || Values->Num() != 3)
    {
        return false;
    }
    if ((*Values)[0]->Type != EJson::Number || (*Values)[1]->Type != EJson::Number
        || (*Values)[2]->Type != EJson::Number)
    {
        return false;
    }
    const double X = (*Values)[0]->AsNumber();
    const double Y = (*Values)[1]->AsNumber();
    const double Z = (*Values)[2]->AsNumber();
    if (!FMath::IsFinite(X) || !FMath::IsFinite(Y) || !FMath::IsFinite(Z))
    {
        return false;
    }
    Out = FVector(X, Y, Z);
    return true;
}

bool ReadQuaternion(const TSharedPtr<FJsonObject>& Object, FQuat& Out)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (!Object.IsValid() || !Object->TryGetArrayField(TEXT("orientation_xyzw"), Values)
        || Values == nullptr || Values->Num() != 4)
    {
        return false;
    }
    if ((*Values)[0]->Type != EJson::Number || (*Values)[1]->Type != EJson::Number
        || (*Values)[2]->Type != EJson::Number || (*Values)[3]->Type != EJson::Number)
    {
        return false;
    }
    const double X = (*Values)[0]->AsNumber();
    const double Y = (*Values)[1]->AsNumber();
    const double Z = (*Values)[2]->AsNumber();
    const double W = (*Values)[3]->AsNumber();
    if (!FMath::IsFinite(X) || !FMath::IsFinite(Y) || !FMath::IsFinite(Z)
        || !FMath::IsFinite(W))
    {
        return false;
    }
    Out = FQuat(X, Y, Z, W);
    if (Out.SizeSquared() < 1e-10)
    {
        return false;
    }
    Out.Normalize();
    return true;
}

bool ParseTrack(const TSharedPtr<FJsonObject>& Track, FTacticalTrackSnapshot& Out)
{
    if (!ReadRequiredString(Track, TEXT("id"), Out.Id)
        || !ReadRequiredString(Track, TEXT("role"), Out.Role)
        || !ReadRequiredString(Track, TEXT("asset_id"), Out.AssetId)
        || !ReadRequiredString(Track, TEXT("type"), Out.Type)
        || !ReadVector(Track, TEXT("position_enu_m"), Out.PositionEnuMetres)
        || !ReadVector(Track, TEXT("velocity_enu_mps"), Out.VelocityEnuMetresPerSecond)
        || !ReadQuaternion(Track, Out.OrientationEnu))
    {
        return false;
    }
    if (!ReadFiniteNumber(Track, TEXT("heading_deg"), Out.HeadingDegrees))
    {
        // Raw local simulator packets do not need a presentation bridge. The
        // supplied attitude remains authoritative; this compass value is only
        // a defensive fallback for a malformed attitude on a later frame.
        Out.HeadingDegrees = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(
            Out.VelocityEnuMetresPerSecond.X,
            Out.VelocityEnuMetresPerSecond.Y)) + 360.0, 360.0);
    }
    return true;
}
}

UTacticalTelemetryComponent::UTacticalTelemetryComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    TrackActorClass = AAegisTacticalTrackActor::StaticClass();
}

void UTacticalTelemetryComponent::BeginPlay()
{
    Super::BeginPlay();
    OpenSocket();
    if (GetWorld() != nullptr)
    {
        TacticalCamera = GetWorld()->SpawnActor<AAegisTacticalCameraActor>();
        HideStaticTrackDuplicates();
    }
}

void UTacticalTelemetryComponent::HideStaticTrackDuplicates()
{
    if (GetWorld() == nullptr)
    {
        return;
    }
    for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
    {
        UStaticMeshComponent* MeshComponent = It->GetStaticMeshComponent();
        UStaticMesh* Mesh = MeshComponent != nullptr ? MeshComponent->GetStaticMesh() : nullptr;
        if (Mesh == nullptr)
        {
            continue;
        }
        const FString AssetPath = Mesh->GetPathName();
        if (AssetPath.Contains(TEXT("/Aegis/Imported/Shahed136/"), ESearchCase::IgnoreCase)
            || AssetPath.Contains(TEXT("/Aegis/Vehicles/SM_Interceptor"), ESearchCase::IgnoreCase))
        {
            // Imported vehicles are preview assets in the map. At runtime
            // their telemetry-driven AAegisTacticalTrackActor is the only
            // vehicle visual, preventing a stationary duplicate in mid-air.
            if (It->IsHidden())
            {
                continue;
            }
            It->SetActorHiddenInGame(true);
            MeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            UE_LOG(LogAegisTacticalViewer, Log,
                TEXT("Hid static vehicle preview %s; awaiting telemetry track"), *AssetPath);
        }
    }
}

void UTacticalTelemetryComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    CloseSocket();
    Super::EndPlay(EndPlayReason);
}

void UTacticalTelemetryComponent::OpenSocket()
{
    Socket = FUdpSocketBuilder(TEXT("AegisTacticalTelemetry"))
        .AsNonBlocking()
        .AsReusable()
        .BoundToAddress(FIPv4Address::InternalLoopback)
        .BoundToPort(ListenPort)
        .WithReceiveBufferSize(MaxDatagramBytes * 4);

    if (Socket == nullptr)
    {
        UE_LOG(LogAegisTacticalViewer, Error,
            TEXT("Unable to bind local tactical telemetry UDP port %d"), ListenPort);
        return;
    }
    UE_LOG(LogAegisTacticalViewer, Log,
        TEXT("Listening for local aegis.tactical.v1 telemetry on 127.0.0.1:%d"), ListenPort);
}

void UTacticalTelemetryComponent::CloseSocket()
{
    if (Socket != nullptr)
    {
        Socket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Socket);
        Socket = nullptr;
    }
}

void UTacticalTelemetryComponent::TickComponent(float DeltaTime, ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    // World Partition can stream editor-preview meshes after BeginPlay.  Keep
    // a short, inexpensive sweep so a static imported Shahed can never be
    // mistaken for the authoritative telemetry-driven aircraft.
    StaticPreviewSweepSeconds += DeltaTime;
    if (StaticPreviewSweepSeconds >= 1.0f)
    {
        // Streaming is asynchronous in the authored World Partition map.
        // Re-run this only once per second, not per telemetry packet.
        HideStaticTrackDuplicates();
        StaticPreviewSweepSeconds = 0.0f;
    }
    const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
    const bool bLinkStale = Health.IsStale(Now);
    for (const TPair<FString, TObjectPtr<AAegisTacticalTrackActor>>& Pair : TrackActors)
    {
        if (Pair.Value != nullptr)
        {
            Pair.Value->SetLinkStale(bLinkStale);
        }
    }
    if (Socket == nullptr)
    {
        return;
    }

    uint32 PendingSize = 0;
    int32 Processed = 0;
    while (Processed++ < 64 && Socket->HasPendingData(PendingSize))
    {
        if (PendingSize == 0 || PendingSize > MaxDatagramBytes)
        {
            TArray<uint8> Discard;
            Discard.SetNumUninitialized(FMath::Min<uint32>(PendingSize, MaxDatagramBytes));
            int32 BytesDiscarded = 0;
            Socket->Recv(Discard.GetData(), Discard.Num(), BytesDiscarded);
            ++Health.RejectedPackets;
            RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
            continue;
        }

        TArray<uint8> Data;
        Data.SetNumUninitialized(PendingSize);
        int32 BytesRead = 0;
        if (!Socket->Recv(Data.GetData(), Data.Num(), BytesRead) || BytesRead <= 0)
        {
            break;
        }
        ++Health.ReceivedPackets;
        FUTF8ToTCHAR Converter(reinterpret_cast<const ANSICHAR*>(Data.GetData()), BytesRead);
        HandlePacket(FString(Converter.Length(), Converter.Get()));
    }
}

bool UTacticalTelemetryComponent::HandlePacket(const FString& Json)
{
    TSharedPtr<FJsonObject> Root;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
    {
        ++Health.RejectedPackets;
        RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
        return false;
    }

    FString Schema;
    FString BridgeSchema;
    FString Status;
    FString Site;
    double Sequence = -1.0;
    double MissionTime = -1.0;
    const TSharedPtr<FJsonObject>* Tracks = nullptr;
    const TSharedPtr<FJsonObject>* Simulation = nullptr;
    const bool bHasBridgeSchema = Root->HasField(TEXT("bridge_schema"));
    const bool bValidBridgeSchema = !bHasBridgeSchema
        || (Root->TryGetStringField(TEXT("bridge_schema"), BridgeSchema)
            && BridgeSchema == TEXT("aegis.unreal-bridge.v1"));
    if (!ReadRequiredString(Root, TEXT("schema"), Schema)
        || Schema != TEXT("aegis.tactical.v1")
        || !bValidBridgeSchema
        || !ReadRequiredString(Root, TEXT("status"), Status)
        || !ReadRequiredString(Root, TEXT("site"), Site)
        || !ReadFiniteNumber(Root, TEXT("sequence"), Sequence)
        || !ReadFiniteNumber(Root, TEXT("mission_time_s"), MissionTime)
        || !Root->TryGetObjectField(TEXT("tracks"), Tracks)
        || Tracks == nullptr || !Tracks->IsValid()
        || Sequence < 0.0 || MissionTime < 0.0
        || !FMath::IsNearlyEqual(Sequence, static_cast<double>(FMath::RoundToInt64(Sequence))))
    {
        ++Health.RejectedPackets;
        RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
        return false;
    }

    double RequestedRate = 1.0;
    double AchievedRealtimeFactor = 0.0;
    double InterceptorSpeedCap = 0.0;
    double GuidanceNavigationGain = 0.0;
    double GuidanceCommandSpeed = 0.0;
    double GuidanceClosingSpeed = 0.0;
    double GuidanceLosRate = 0.0;
    double GuidanceTrackConfidence = 0.0;
    double AiResidualAuthority = 0.0;
    FString InterceptorProfileEvidence = TEXT("UNKNOWN");
    FString GuidanceMode = TEXT("WAITING");
    if (Root->TryGetObjectField(TEXT("simulation"), Simulation)
        && Simulation != nullptr && Simulation->IsValid())
    {
        if (!ReadFiniteNumber(*Simulation, TEXT("requested_rate"), RequestedRate)
            || !ReadFiniteNumber(*Simulation, TEXT("achieved_realtime_factor"), AchievedRealtimeFactor)
            || !ReadFiniteNumber(*Simulation, TEXT("interceptor_speed_cap_mps"), InterceptorSpeedCap)
            || !ReadRequiredString(*Simulation, TEXT("interceptor_profile_evidence"), InterceptorProfileEvidence)
            || RequestedRate <= 0.0 || AchievedRealtimeFactor < 0.0 || InterceptorSpeedCap <= 0.0)
        {
            ++Health.RejectedPackets;
            RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
            return false;
        }
        const auto ReadOptionalFinite = [&Simulation](
            const TCHAR* Field,
            double& Value)
        {
            return !(*Simulation)->HasField(Field)
                || ReadFiniteNumber(*Simulation, Field, Value);
        };
        if (((*Simulation)->HasField(TEXT("guidance_mode"))
                && !(*Simulation)->TryGetStringField(TEXT("guidance_mode"), GuidanceMode))
            || !ReadOptionalFinite(TEXT("navigation_gain"), GuidanceNavigationGain)
            || !ReadOptionalFinite(TEXT("command_speed_mps"), GuidanceCommandSpeed)
            || !ReadOptionalFinite(TEXT("closing_speed_mps"), GuidanceClosingSpeed)
            || !ReadOptionalFinite(TEXT("los_rate_dps"), GuidanceLosRate)
            || !ReadOptionalFinite(TEXT("track_confidence"), GuidanceTrackConfidence)
            || !ReadOptionalFinite(TEXT("ai_residual_authority"), AiResidualAuthority)
            || GuidanceNavigationGain < 0.0 || GuidanceNavigationGain > 10.0
            || GuidanceCommandSpeed < 0.0 || GuidanceCommandSpeed > 250.0
            || FMath::Abs(GuidanceClosingSpeed) > 500.0
            || GuidanceLosRate < 0.0 || GuidanceLosRate > 720.0
            || GuidanceTrackConfidence < 0.0 || GuidanceTrackConfidence > 1.0
            || AiResidualAuthority < 0.0 || AiResidualAuthority > 1.0)
        {
            ++Health.RejectedPackets;
            RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
            return false;
        }
    }

    bool bRadarLocked = false;
    bool bEoLocked = false;
    bool bRadarFailure = false;
    bool bEoFailure = false;
    bool bActuatorFailure = false;
    FString FusionSource = TEXT("SEARCHING");
    const TSharedPtr<FJsonObject>* Sensors = nullptr;
    if (Root->TryGetObjectField(TEXT("sensors"), Sensors)
        && Sensors != nullptr && Sensors->IsValid())
    {
        if (!(*Sensors)->TryGetBoolField(TEXT("radar_locked"), bRadarLocked)
            || !(*Sensors)->TryGetBoolField(TEXT("eo_locked"), bEoLocked)
            || !ReadRequiredString(*Sensors, TEXT("fusion_source"), FusionSource))
        {
            ++Health.RejectedPackets;
            RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
            return false;
        }
        (*Sensors)->TryGetBoolField(TEXT("radar_failure"), bRadarFailure);
        (*Sensors)->TryGetBoolField(TEXT("eo_failure"), bEoFailure);
        (*Sensors)->TryGetBoolField(TEXT("actuator_failure"), bActuatorFailure);
    }

    FString EnvironmentName = TEXT("CLEAR");
    double VisibilityMetres = 0.0;
    FVector WindEnuMetresPerSecond = FVector::ZeroVector;
    const TSharedPtr<FJsonObject>* Environment = nullptr;
    if (Root->TryGetObjectField(TEXT("environment"), Environment)
        && Environment != nullptr && Environment->IsValid())
    {
        if (!ReadRequiredString(*Environment, TEXT("name"), EnvironmentName)
            || !ReadFiniteNumber(*Environment, TEXT("visibility_m"), VisibilityMetres)
            || VisibilityMetres < 0.0
            || !ReadVector(*Environment, TEXT("wind_enu_mps"), WindEnuMetresPerSecond))
        {
            ++Health.RejectedPackets;
            RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
            return false;
        }
    }

    FString ScenarioIntruder = TEXT("UNKNOWN");
    FString ScenarioPattern = TEXT("UNKNOWN");
    FString ScenarioPad = TEXT("MID");
    bool bRecording = false;
    const TSharedPtr<FJsonObject>* Scenario = nullptr;
    if (Root->TryGetObjectField(TEXT("scenario"), Scenario)
        && Scenario != nullptr && Scenario->IsValid())
    {
        if (!ReadRequiredString(*Scenario, TEXT("intruder"), ScenarioIntruder)
            || !ReadRequiredString(*Scenario, TEXT("pattern"), ScenarioPattern)
            || !ReadRequiredString(*Scenario, TEXT("pad"), ScenarioPad)
            || !(*Scenario)->TryGetBoolField(TEXT("recording"), bRecording))
        {
            ++Health.RejectedPackets;
            RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
            return false;
        }
    }

    FVector PredictedIntercept = FVector::ZeroVector;
    bool bHasPredictedIntercept = false;
    if (const TSharedPtr<FJsonValue>* PredictedValue =
        Root->Values.Find(TEXT("predicted_intercept_enu_m")))
    {
        if ((*PredictedValue)->Type != EJson::Null)
        {
            if (!ReadVector(Root, TEXT("predicted_intercept_enu_m"), PredictedIntercept))
            {
                ++Health.RejectedPackets;
                RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
                return false;
            }
            bHasPredictedIntercept = true;
        }
    }

    const int64 PacketSequence = FMath::RoundToInt64(Sequence);
    // The simulator deliberately starts a fresh integer sequence epoch for a
    // new recorded/demo mission. Accept that only when the relative mission
    // clock has also restarted near zero; ordinary duplicated or re-ordered
    // UDP stays rejected.
    const bool bNewMissionEpoch = Health.LastSequence >= 0
        && PacketSequence <= 2
        && PacketSequence < Health.LastSequence
        && MissionTime <= 1.0
        && Health.LastMissionTimeSeconds >= 5.0;
    if (bNewMissionEpoch)
    {
        Health.LastSequence = -1;
        LastSequence = -1;
        Health.LastMissionTimeSeconds = -1.0;
    }

    if (PacketSequence <= Health.LastSequence
        || (Health.LastMissionTimeSeconds >= 0.0 && MissionTime < Health.LastMissionTimeSeconds))
    {
        ++Health.RejectedPackets;
        RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
        return false;
    }

    const TSharedPtr<FJsonObject>* IntruderObject = nullptr;
    if (!(*Tracks)->TryGetObjectField(TEXT("intruder"), IntruderObject)
        || IntruderObject == nullptr || !IntruderObject->IsValid())
    {
        ++Health.RejectedPackets;
        RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
        return false;
    }

    FTacticalTrackSnapshot Intruder;
    if (!ParseTrack(*IntruderObject, Intruder))
    {
        ++Health.RejectedPackets;
        RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
        return false;
    }

    const TSharedPtr<FJsonValue>* InterceptorValue = (*Tracks)->Values.Find(TEXT("interceptor"));
    FTacticalTrackSnapshot Interceptor;
    bool bHasInterceptor = false;
    if (InterceptorValue == nullptr || !InterceptorValue->IsValid())
    {
        ++Health.RejectedPackets;
        RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
        return false;
    }
    if ((*InterceptorValue)->Type != EJson::Null)
    {
        const TSharedPtr<FJsonObject> InterceptorObject = (*InterceptorValue)->AsObject();
        if (!ParseTrack(InterceptorObject, Interceptor))
        {
            ++Health.RejectedPackets;
            RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
            return false;
        }
        bHasInterceptor = true;
    }

    Health.DroppedPackets += Health.LastSequence >= 0
        ? FMath::Max<int64>(0, PacketSequence - Health.LastSequence - 1) : 0;
    const bool bTransitionedToIntercepted = (Health.Status != TEXT("INTERCEPTED") && Status == TEXT("INTERCEPTED"));
    Health.LastSequence = PacketSequence;
    LastSequence = PacketSequence;
    Health.LastMissionTimeSeconds = MissionTime;
    Health.LastReceiveWorldSeconds = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
    Health.Status = Status;
    Health.Site = Site;
    Health.RequestedSimulationRate = RequestedRate;
    Health.AchievedRealtimeFactor = AchievedRealtimeFactor;
    Health.InterceptorSpeedCapMps = InterceptorSpeedCap;
    Health.InterceptorProfileEvidence = InterceptorProfileEvidence;
    Health.GuidanceMode = GuidanceMode;
    Health.GuidanceNavigationGain = GuidanceNavigationGain;
    Health.GuidanceCommandSpeedMps = GuidanceCommandSpeed;
    Health.GuidanceClosingSpeedMps = GuidanceClosingSpeed;
    Health.GuidanceLosRateDps = GuidanceLosRate;
    Health.GuidanceTrackConfidence = GuidanceTrackConfidence;
    Health.AiResidualAuthority = AiResidualAuthority;
    Health.bRadarLocked = bRadarLocked;
    Health.bEoLocked = bEoLocked;
    Health.bRadarFailure = bRadarFailure;
    Health.bEoFailure = bEoFailure;
    Health.bActuatorFailure = bActuatorFailure;
    Health.FusionSource = FusionSource;
    Health.EnvironmentName = EnvironmentName;
    Health.VisibilityMetres = VisibilityMetres;
    Health.WindEnuMetresPerSecond = WindEnuMetresPerSecond;
    Health.ScenarioIntruder = ScenarioIntruder;
    Health.ScenarioPattern = ScenarioPattern;
    Health.ScenarioPad = ScenarioPad;
    Health.bRecording = bRecording;
    Health.bHasPredictedIntercept = bHasPredictedIntercept;
    Health.PredictedInterceptEnuMetres = PredictedIntercept;
    ++Health.ForwardedPackets;

    if (TacticalCamera != nullptr)
    {
        TacticalCamera->SetMissionPresentationState(Health);
    }

    if (TacticalSite == nullptr && GetWorld() != nullptr)
    {
        TacticalSite = Cast<AAegisTacticalSiteActor>(UGameplayStatics::GetActorOfClass(
            GetWorld(), AAegisTacticalSiteActor::StaticClass()));
    }
    if (TacticalSite != nullptr)
    {
        TacticalSite->SetSensorPresentationState(bRadarLocked, bRadarFailure);
        TacticalSite->SetSensorTrackPresentation(Intruder.PositionEnuMetres);
        TacticalSite->SetPredictedIntercept(
            PredictedIntercept, bHasPredictedIntercept, Status);
    }

    UpdateTrack(Intruder);
    if (bHasInterceptor)
    {
        UpdateTrack(Interceptor);
    }
    else
    {
        MarkRoleAbsent(TEXT("interceptor"));
        if (TacticalCamera != nullptr)
        {
            TacticalCamera->ClearTrack(TEXT("interceptor"));
        }
    }

    // A swarm packet is bridged into the normal focused pair above, then adds
    // its active formation as a presentation-only sidecar. These extra actors
    // make the saturation geometry visible while the primary pair remains the
    // sole camera/HUD focus and no viewer path can affect simulation state.
    const TSharedPtr<FJsonObject>* SwarmPresentation = nullptr;
    if (Root->TryGetObjectField(TEXT("swarm_presentation"), SwarmPresentation)
        && SwarmPresentation != nullptr && SwarmPresentation->IsValid())
    {
        const TArray<TSharedPtr<FJsonValue>>* SwarmTracks = nullptr;
        if (!(*SwarmPresentation)->TryGetArrayField(TEXT("tracks"), SwarmTracks)
            || SwarmTracks == nullptr)
        {
            ++Health.RejectedPackets;
            RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
            return false;
        }
        TSet<FString> IncomingSwarmTrackIds;
        for (const TSharedPtr<FJsonValue>& TrackValue : *SwarmTracks)
        {
            const TSharedPtr<FJsonObject> TrackObject = TrackValue->AsObject();
            FTacticalTrackSnapshot SwarmTrack;
            if (!ParseTrack(TrackObject, SwarmTrack))
            {
                ++Health.RejectedPackets;
                RejectedPacketCount = static_cast<int32>(Health.RejectedPackets);
                return false;
            }
            IncomingSwarmTrackIds.Add(SwarmTrack.Id);
            UpdateTrack(SwarmTrack, false);
        }
        for (const FString& PreviousId : SwarmPresentationTrackIds)
        {
            if (!IncomingSwarmTrackIds.Contains(PreviousId))
            {
                if (TObjectPtr<AAegisTacticalTrackActor>* Actor = TrackActors.Find(PreviousId))
                {
                    if (Actor->Get() != nullptr)
                    {
                        (*Actor)->MarkAbsent();
                    }
                }
            }
        }
        SwarmPresentationTrackIds = MoveTemp(IncomingSwarmTrackIds);
    }
    else if (!SwarmPresentationTrackIds.IsEmpty())
    {
        for (const FString& PreviousId : SwarmPresentationTrackIds)
        {
            if (TObjectPtr<AAegisTacticalTrackActor>* Actor = TrackActors.Find(PreviousId))
            {
                if (Actor->Get() != nullptr)
                {
                    (*Actor)->MarkAbsent();
                }
            }
        }
        SwarmPresentationTrackIds.Reset();
    }

    if (bTransitionedToIntercepted)
    {
        if (EffectsManager == nullptr && GetWorld() != nullptr)
        {
            EffectsManager = Cast<AAegisTacticalEffectsManager>(UGameplayStatics::GetActorOfClass(
                GetWorld(), AAegisTacticalEffectsManager::StaticClass()));
        }
        if (EffectsManager != nullptr)
        {
            if (AAegisTacticalTrackActor* IntruderActor = GetOrCreateTrack(Intruder))
            {
                EffectsManager->SpawnInterceptExplosion(IntruderActor->GetActorLocation());
            }
        }
    }

    return true;
}

void UTacticalTelemetryComponent::UpdateTrack(
    const FTacticalTrackSnapshot& Snapshot, const bool bUpdateCamera)
{
    LatestSnapshotsByRole.Add(Snapshot.Role.ToLower(), Snapshot);
    if (AAegisTacticalTrackActor* Actor = GetOrCreateTrack(Snapshot))
    {
        Actor->ApplySnapshot(Snapshot);
    }
    if (bUpdateCamera && TacticalCamera != nullptr)
    {
        TacticalCamera->SetTrackSnapshot(Snapshot);
    }
}

void UTacticalTelemetryComponent::MarkRoleAbsent(const FString& Role)
{
    LatestSnapshotsByRole.Remove(Role.ToLower());
    for (const TPair<FString, TObjectPtr<AAegisTacticalTrackActor>>& Pair : TrackActors)
    {
        if (Pair.Value != nullptr && Pair.Value->TrackRole.Equals(Role, ESearchCase::IgnoreCase))
        {
            Pair.Value->MarkAbsent();
        }
    }
}

bool UTacticalTelemetryComponent::GetLatestSnapshot(
    const FString& Role, FTacticalTrackSnapshot& OutSnapshot) const
{
    if (const FTacticalTrackSnapshot* Snapshot = LatestSnapshotsByRole.Find(Role.ToLower()))
    {
        OutSnapshot = *Snapshot;
        return true;
    }
    return false;
}

AAegisTacticalTrackActor* UTacticalTelemetryComponent::GetOrCreateTrack(
    const FTacticalTrackSnapshot& Snapshot)
{
    if (TObjectPtr<AAegisTacticalTrackActor>* Existing = TrackActors.Find(Snapshot.Id))
    {
        return Existing->Get();
    }
    if (GetWorld() == nullptr || TrackActorClass == nullptr)
    {
        return nullptr;
    }
    AAegisTacticalTrackActor* Actor = GetWorld()->SpawnActor<AAegisTacticalTrackActor>(TrackActorClass);
    if (Actor != nullptr)
    {
        Actor->TrackRole = Snapshot.Role;
        TrackActors.Add(Snapshot.Id, Actor);
    }
    return Actor;
}
