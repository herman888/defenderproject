#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "AegisTacticalPlayerController.generated.h"

class FSocket;

/** Loopback-only controls for the local Python training simulation. */
UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalPlayerController : public APlayerController
{
    GENERATED_BODY()

public:
    virtual void SetupInputComponent() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

    FString GetLastLocalCommand() const { return LastLocalCommand; }

private:
    void CycleCameraPresentation();
    void ToggleSimulationPause();
    void RestartSimulation();
    void SetSimulationRate1x();
    void SetSimulationRate2x();
    void SetSimulationRate4x();
    void SetSimulationRate8x();
    void ToggleRadarFailure();
    void ToggleEoFailure();
    void ToggleActuatorFailure();
    void ClearFailures();
    void NextScenarioPreset();
    void SetSimulationRate(double Rate);
    void ToggleFailure(const FString& Failure, const FString& Label);
    void SendLocalSimulationCommand(const FString& Json, const FString& Label);

    FSocket* ControlSocket = nullptr;
    FString LastLocalCommand = TEXT("LOCAL SIM ONLY — NO HARDWARE COMMAND PATH");
};
