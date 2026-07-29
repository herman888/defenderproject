#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "AegisTacticalViewerGameMode.generated.h"

class AAegisTacticalTelemetryManager;
class AAegisTacticalSiteActor;

UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalViewerGameMode : public AGameModeBase
{
    GENERATED_BODY()

public:
    AAegisTacticalViewerGameMode();

    virtual void BeginPlay() override;

    UPROPERTY(EditDefaultsOnly, Category = "Telemetry")
    TSubclassOf<AAegisTacticalTelemetryManager> TelemetryManagerClass;

    UPROPERTY(EditDefaultsOnly, Category = "Presentation")
    TSubclassOf<AAegisTacticalSiteActor> SiteActorClass;
};
