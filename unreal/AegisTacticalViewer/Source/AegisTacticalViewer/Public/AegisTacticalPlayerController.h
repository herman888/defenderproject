#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "AegisTacticalPlayerController.generated.h"

/** Minimal local presentation controls; no input is sent to Python. */
UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalPlayerController : public APlayerController
{
    GENERATED_BODY()

public:
    virtual void SetupInputComponent() override;

private:
    void CycleCameraPresentation();
};
