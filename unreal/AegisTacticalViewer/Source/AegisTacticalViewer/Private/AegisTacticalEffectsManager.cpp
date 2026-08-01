#include "AegisTacticalEffectsManager.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraComponent.h"
#include "Components/PointLightComponent.h"
#include "Engine/World.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogAegisTacticalViewer, Log, All);

AAegisTacticalEffectsManager::AAegisTacticalEffectsManager()
{
    PrimaryActorTick.bCanEverTick = false;
}

void AAegisTacticalEffectsManager::SpawnInterceptExplosion(FVector WorldLocation, float Scale)
{
    UNiagaraSystem* System = InterceptExplosionSystem.LoadSynchronous();
    if (System != nullptr)
    {
        UNiagaraFunctionLibrary::SpawnSystemAtLocation(
            GetWorld(),
            System,
            WorldLocation,
            FRotator::ZeroRotator,
            FVector(Scale)
        );
        UE_LOG(LogAegisTacticalViewer, Log, TEXT("Spawned intercept explosion at %s"), *WorldLocation.ToString());
    }
    else
    {
        UE_LOG(LogAegisTacticalViewer, Warning, TEXT("No InterceptExplosionSystem set, spawning fallback flash."));
        SpawnFallbackFlash(WorldLocation);
    }
}

void AAegisTacticalEffectsManager::SpawnRocketLaunchSmoke(FVector WorldLocation, FRotator LaunchDirection)
{
    UNiagaraSystem* System = RocketLaunchSmokeSystem.LoadSynchronous();
    if (System != nullptr)
    {
        UNiagaraFunctionLibrary::SpawnSystemAtLocation(
            GetWorld(),
            System,
            WorldLocation,
            LaunchDirection
        );
        UE_LOG(LogAegisTacticalViewer, Log, TEXT("Spawned rocket launch smoke at %s"), *WorldLocation.ToString());
    }
}

void AAegisTacticalEffectsManager::SpawnFallbackFlash(FVector WorldLocation)
{
    if (UWorld* World = GetWorld())
    {
        AActor* FlashActor = World->SpawnActor<AActor>(WorldLocation, FRotator::ZeroRotator);
        if (FlashActor)
        {
            UPointLightComponent* LightComp = NewObject<UPointLightComponent>(FlashActor);
            LightComp->RegisterComponent();
            LightComp->AttachToComponent(FlashActor->GetRootComponent(), FAttachmentTransformRules::KeepRelativeTransform);
            
            LightComp->SetIntensity(50000.0f);
            LightComp->SetAttenuationRadius(2000.0f);
            LightComp->SetLightColor(FLinearColor(1.0f, 0.5f, 0.0f)); // white-orange

            FlashActor->SetLifeSpan(FallbackFlashDuration);
        }
    }
}
