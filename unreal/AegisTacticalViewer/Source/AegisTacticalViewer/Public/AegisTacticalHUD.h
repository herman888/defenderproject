#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "AegisTacticalHUD.generated.h"

/** Read-only on-screen status for the local presentation client. */
UCLASS()
class AEGISTACTICALVIEWER_API AAegisTacticalHUD : public AHUD
{
    GENERATED_BODY()

public:
    virtual void DrawHUD() override;
};
