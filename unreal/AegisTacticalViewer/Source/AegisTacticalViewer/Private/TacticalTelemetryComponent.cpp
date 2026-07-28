#include "TacticalTelemetryComponent.h"

#include "AegisTacticalCameraActor.h"
#include "AegisTacticalViewer.h"
#include "Common/UdpSocketBuilder.h"
#include "Containers/StringConv.h"
#include "Dom/JsonObject.h"
#include "Interfaces/IPv4/IPv4Address.h"
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
    return ReadRequiredString(Track, TEXT("id"), Out.Id)
        && ReadRequiredString(Track, TEXT("role"), Out.Role)
        && ReadRequiredString(Track, TEXT("asset_id"), Out.AssetId)
        && ReadRequiredString(Track, TEXT("type"), Out.Type)
        && ReadVector(Track, TEXT("position_enu_m"), Out.PositionEnuMetres)
        && ReadVector(Track, TEXT("velocity_enu_mps"), Out.VelocityEnuMetresPerSecond)
        && ReadQuaternion(Track, Out.OrientationEnu)
        && ReadFiniteNumber(Track, TEXT("heading_deg"), Out.HeadingDegrees);
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
        TEXT("Listening for local aegis.unreal-bridge.v1 telemetry on 127.0.0.1:%d"), ListenPort);
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
    if (!ReadRequiredString(Root, TEXT("schema"), Schema)
        || Schema != TEXT("aegis.tactical.v1")
        || !ReadRequiredString(Root, TEXT("bridge_schema"), BridgeSchema)
        || BridgeSchema != TEXT("aegis.unreal-bridge.v1")
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

    const int64 PacketSequence = FMath::RoundToInt64(Sequence);
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
    Health.LastSequence = PacketSequence;
    LastSequence = PacketSequence;
    Health.LastMissionTimeSeconds = MissionTime;
    Health.LastReceiveWorldSeconds = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
    Health.Status = Status;
    Health.Site = Site;
    ++Health.ForwardedPackets;

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
    return true;
}

void UTacticalTelemetryComponent::UpdateTrack(const FTacticalTrackSnapshot& Snapshot)
{
    if (AAegisTacticalTrackActor* Actor = GetOrCreateTrack(Snapshot))
    {
        Actor->ApplySnapshot(Snapshot);
    }
    if (TacticalCamera != nullptr)
    {
        TacticalCamera->SetTrackWorldPosition(
            Snapshot.Role, AAegisTacticalTrackActor::EnuToUnrealWorld(Snapshot.PositionEnuMetres));
    }
}

void UTacticalTelemetryComponent::MarkRoleAbsent(const FString& Role)
{
    for (const TPair<FString, TObjectPtr<AAegisTacticalTrackActor>>& Pair : TrackActors)
    {
        if (Pair.Value != nullptr && Pair.Value->TrackRole.Equals(Role, ESearchCase::IgnoreCase))
        {
            Pair.Value->MarkAbsent();
        }
    }
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
