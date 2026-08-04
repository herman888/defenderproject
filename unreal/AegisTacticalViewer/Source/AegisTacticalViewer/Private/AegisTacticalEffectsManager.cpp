#include "AegisTacticalEffectsManager.h"

#include "AegisTacticalViewer.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"

AAegisTacticalEffectsManager::AAegisTacticalEffectsManager()
{
    PrimaryActorTick.bCanEverTick = false;
}

void AAegisTacticalEffectsManager::SpawnInterceptExplosion(FVector WorldLocation, float Scale)
{
    UNiagaraSystem* System = InterceptExplosionSystem.LoadSynchronous();
    if (System == nullptr)
    {
        // Expected until Niagara content is authored, so log verbosely rather
        // than as a warning - this is the normal path today, not a fault.
        UE_LOG(LogAegisTacticalViewer, Verbose,
               TEXT("No InterceptExplosionSystem assigned; using fallback flash."));
        SpawnFallbackFlash(WorldLocation);
        return;
    }

    UNiagaraFunctionLibrary::SpawnSystemAtLocation(
        GetWorld(),
        System,
        WorldLocation,
        FRotator::ZeroRotator,
        FVector(Scale));

    UE_LOG(LogAegisTacticalViewer, Log,
           TEXT("Spawned intercept explosion at %s"), *WorldLocation.ToString());
}

void AAegisTacticalEffectsManager::SpawnFallbackFlash(FVector WorldLocation)
{
    UWorld* World = GetWorld();
    if (World == nullptr)
    {
        return;
    }

    AActor* FlashActor = World->SpawnActor<AActor>(WorldLocation, FRotator::ZeroRotator);
    if (FlashActor == nullptr)
    {
        return;
    }

    // A bare AActor has no RootComponent, so one must be created before
    // anything can attach to it. Without this the light attaches to nullptr and
    // is never positioned at the intercept point.
    USceneComponent* Root = NewObject<USceneComponent>(FlashActor, TEXT("FlashRoot"));
    Root->SetMobility(EComponentMobility::Movable);
    FlashActor->SetRootComponent(Root);
    Root->RegisterComponent();

    UPointLightComponent* Light = NewObject<UPointLightComponent>(FlashActor, TEXT("FlashLight"));
    // Runtime-spawned lights must be Movable; a Static light cannot be created
    // outside the lighting build.
    Light->SetMobility(EComponentMobility::Movable);
    Light->AttachToComponent(Root, FAttachmentTransformRules::KeepRelativeTransform);
    Light->RegisterComponent();

    Light->SetIntensity(FallbackFlashIntensity);
    Light->SetAttenuationRadius(FallbackFlashRadius);
    Light->SetLightColor(FLinearColor(1.0f, 0.5f, 0.0f));
    Light->SetCastShadows(false);

    FlashActor->SetActorLocation(WorldLocation);
    FlashActor->SetLifeSpan(FallbackFlashDuration);
}
