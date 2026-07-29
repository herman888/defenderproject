#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "AegisTacticalPlayerController.generated.h"

class FSocket;

/** Minimal local presentation controls; no input is sent to Python. */
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
    void SetSimulationRate(double Rate);
    void SendLocalSimulationCommand(const FString& Json, const FString& Label);

    FSocket* ControlSocket = nullptr;
    FString LastLocalCommand = TEXT("LOCAL SIM ONLY — NO HARDWARE COMMAND PATH");
};
