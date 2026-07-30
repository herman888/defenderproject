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

    /** Small non-authoritative silhouette pieces used until a Fab mesh is assigned. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TObjectPtr<UStaticMeshComponent> MainWing;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TObjectPtr<UStaticMeshComponent> TailWing;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TObjectPtr<UStaticMeshComponent> VerticalFin;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TObjectPtr<UStaticMeshComponent> EngineGlow;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TArray<TObjectPtr<UStaticMeshComponent>> RotorArms;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Visual")
    TArray<TObjectPtr<UStaticMeshComponent>> RotorBlades;

private:
    void ApplyVisualDefinition(const FTacticalTrackSnapshot& Snapshot);
    void SetDisplayColor(const FLinearColor& Color);
    void AddTrailPoint(const FVector& WorldLocation);

    FVector InterpolationStartLocation = FVector::ZeroVector;
    FVector TargetLocation = FVector::ZeroVector;
    FQuat InterpolationStartRotation = FQuat::Identity;
    FQuat TargetRotation = FQuat::Identity;
    TArray<FVector> TrailPoints;
    TObjectPtr<UMaterialInterface> ShapeMaterial;
    TObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;
    FLinearColor BaseColor = FLinearColor::White;
    FString AppliedVisualKey;
    FString DisplayName;
    float LastSnapshotTime = -BIG_NUMBER;
    float PreviousSnapshotTime = -BIG_NUMBER;
    float InterpolationElapsed = 0.0f;
    float InterpolationDuration = 0.05f;
    bool bAbsent = false;
    bool bHasSnapshot = false;
    bool bLastLinkStale = false;
    bool bUsesRotors = false;
};
