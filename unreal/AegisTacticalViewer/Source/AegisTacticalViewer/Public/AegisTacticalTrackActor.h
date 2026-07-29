#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TacticalTypes.h"
#include "AegisTacticalTrackActor.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UStaticMeshComponent;
class UTextRenderComponent;

/** A display-only actor driven by one tactical telemetry track. */
UCLASS(Blueprintable)
class AEGISTACTICALVIEWER_API AAegisTacticalTrackActor : public AActor
{
    GENERATED_BODY()

public:
    AAegisTacticalTrackActor();

    virtual void Tick(float DeltaSeconds) override;

    /** Apply validated display telemetry; this actor never controls the sim. */
    void ApplySnapshot(const FTacticalTrackSnapshot& Snapshot);
    void MarkAbsent();
    void SetLinkStale(bool bLinkStale);

    static FVector EnuToUnrealWorld(const FVector& EnuMetres);
    static FRotator EnuOrientationToUnreal(const FQuat& OrientationEnu,
        double HeadingDegrees);

    UPROPERTY(BlueprintReadOnly, Category = "Telemetry")
    FString TrackRole;

    UPROPERTY(BlueprintReadOnly, Category = "Telemetry")
    bool bIsStale = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry")
    float StaleAfterSeconds = 5.0f;

protected:
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TObjectPtr<UStaticMeshComponent> Visual;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TObjectPtr<UTextRenderComponent> Label;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TObjectPtr<UInstancedStaticMeshComponent> Trail;

private:
    void ApplyVisualDefinition(const FTacticalTrackSnapshot& Snapshot);
    void SetDisplayColor(const FLinearColor& Color);
    void AddTrailPoint(const FVector& WorldLocation);

    FVector TargetLocation = FVector::ZeroVector;
    FRotator TargetRotation = FRotator::ZeroRotator;
    TArray<FVector> TrailPoints;
    TObjectPtr<UMaterialInterface> ShapeMaterial;
    TObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;
    FLinearColor BaseColor = FLinearColor::White;
    float LastSnapshotTime = -BIG_NUMBER;
    bool bAbsent = false;
    bool bLastLinkStale = false;
};
