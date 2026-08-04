#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AegisTacticalEffectsManager.generated.h"

class UNiagaraSystem;

/**
 * Manages spawning of tactical visual effects.
 *
 * This is display-only; it never affects simulation state. Python remains the
 * authoritative source of truth and the viewer has no return path, so nothing
 * here can influence an engagement outcome.
 *
 * Effects for deferred workstreams (for example rocket launch smoke) are
 * deliberately absent - see docs-internal/PROGRAM_PLAN.md section 4.
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

    /** The Niagara system to use for intercept explosions. Set in Blueprint or editor. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Effects")
    TSoftObjectPtr<UNiagaraSystem> InterceptExplosionSystem;

    /** Fallback flash duration when no Niagara system is assigned. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Effects")
    float FallbackFlashDuration = 0.15f;

    /** Fallback flash intensity, in candelas. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Effects")
    float FallbackFlashIntensity = 50000.0f;

    /** Fallback flash attenuation radius, in centimetres. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Effects")
    float FallbackFlashRadius = 2000.0f;

private:
    /** Spawn a fallback point-light flash when no Niagara system is available. */
    void SpawnFallbackFlash(FVector WorldLocation);
};
