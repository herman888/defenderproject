#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AegisTacticalTelemetryManager.generated.h"

class UTacticalTelemetryComponent;
class USceneComponent;

/** Owns the UDP receiver spawned by the viewer's game mode. */
UCLASS(Blueprintable)
class AEGISTACTICALVIEWER_API AAegisTacticalTelemetryManager : public AActor
{
    GENERATED_BODY()

public:
    AAegisTacticalTelemetryManager();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Telemetry")
    TObjectPtr<USceneComponent> SceneRoot;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Telemetry")
    TObjectPtr<UTacticalTelemetryComponent> Telemetry;
};
