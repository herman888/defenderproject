#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AegisTacticalEffectsManager.generated.h"

class UNiagaraSystem;
class UNiagaraComponent;

/**
 * Manages spawning and pooling of tactical visual effects.
 * This is display-only; it never affects simulation state.
 */
UCLASS(Blueprintable)
class AEGISTACTICALVIEWER_API AAegisTacticalEffectsManager : public AActor
{
    GENERATED_BODY()

public:
    AAegisTacticalEffectsManager();

    /** Spawn an intercept explosion effect at the given world location. */
    UFUNCTION(BlueprintCallable, Category = "Effects")
    void SpawnInterceptExplosion(FVector WorldLocation, float Scale = 1.0f);

    /** Spawn a rocket launch smoke effect at the given world location. */
    UFUNCTION(BlueprintCallable, Category = "Effects")
    void SpawnRocketLaunchSmoke(FVector WorldLocation, FRotator LaunchDirection);

    /** The Niagara system to use for intercept explosions. Set in Blueprint or editor. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Effects")
    TSoftObjectPtr<UNiagaraSystem> InterceptExplosionSystem;

    /** The Niagara system to use for rocket launch smoke. Set in Blueprint or editor. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Effects")
    TSoftObjectPtr<UNiagaraSystem> RocketLaunchSmokeSystem;

    /** Fallback flash duration when no Niagara system is assigned. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Effects")
    float FallbackFlashDuration = 0.15f;

private:
    /** Spawn a fallback point light flash when Niagara system is not available. */
    void SpawnFallbackFlash(FVector WorldLocation);
};
