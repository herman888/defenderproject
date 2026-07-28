#include "AegisTacticalViewerGameMode.h"

#include "AegisTacticalHUD.h"
#include "AegisTacticalPlayerController.h"
#include "AegisTacticalTelemetryManager.h"
#include "Engine/World.h"

AAegisTacticalViewerGameMode::AAegisTacticalViewerGameMode()
{
    HUDClass = AAegisTacticalHUD::StaticClass();
    PlayerControllerClass = AAegisTacticalPlayerController::StaticClass();
}

void AAegisTacticalViewerGameMode::BeginPlay()
{
    Super::BeginPlay();

    if (TelemetryManagerClass == nullptr)
    {
        TelemetryManagerClass = AAegisTacticalTelemetryManager::StaticClass();
    }
    GetWorld()->SpawnActor<AAegisTacticalTelemetryManager>(TelemetryManagerClass);
}
