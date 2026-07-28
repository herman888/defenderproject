#include "AegisTacticalTelemetryManager.h"

#include "Components/SceneComponent.h"
#include "TacticalTelemetryComponent.h"

AAegisTacticalTelemetryManager::AAegisTacticalTelemetryManager()
{
    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    RootComponent = SceneRoot;
    Telemetry = CreateDefaultSubobject<UTacticalTelemetryComponent>(TEXT("Telemetry"));
}
