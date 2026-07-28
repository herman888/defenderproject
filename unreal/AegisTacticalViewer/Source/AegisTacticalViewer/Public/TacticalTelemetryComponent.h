#pragma once

#include "AegisTacticalTrackActor.h"
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "TacticalTypes.h"
#include "TacticalTelemetryComponent.generated.h"

class FSocket;
class FJsonObject;
class AAegisTacticalCameraActor;

/** Receives display-only aegis.unreal-bridge.v1 UDP telemetry. */
UCLASS(ClassGroup = (Aegis), meta = (BlueprintSpawnableComponent))
class AEGISTACTICALVIEWER_API UTacticalTelemetryComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UTacticalTelemetryComponent();

    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void TickComponent(float DeltaTime, ELevelTick TickType,
        FActorComponentTickFunction* ThisTickFunction) override;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry")
    int32 ListenPort = 8788;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry")
    TSubclassOf<AAegisTacticalTrackActor> TrackActorClass;

    UPROPERTY(BlueprintReadOnly, Category = "Telemetry")
    int64 LastSequence = -1;

    UPROPERTY(BlueprintReadOnly, Category = "Telemetry")
    int32 RejectedPacketCount = 0;

    const FTacticalTelemetryHealth& GetHealth() const { return Health; }

#if WITH_DEV_AUTOMATION_TESTS
    /** Test seam for the exact production packet parser; it never opens a socket. */
    bool ProcessPacketForAutomation(const FString& Json) { return HandlePacket(Json); }
#endif

private:
    static constexpr int32 MaxDatagramBytes = 65507;

    void OpenSocket();
    void CloseSocket();
    bool HandlePacket(const FString& Json);
    void UpdateTrack(const FTacticalTrackSnapshot& Snapshot);
    void MarkRoleAbsent(const FString& Role);
    AAegisTacticalTrackActor* GetOrCreateTrack(const FTacticalTrackSnapshot& Snapshot);

    FSocket* Socket = nullptr;
    TMap<FString, TObjectPtr<AAegisTacticalTrackActor>> TrackActors;
    TObjectPtr<AAegisTacticalCameraActor> TacticalCamera;
    FTacticalTelemetryHealth Health;
};
