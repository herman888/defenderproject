#include "AegisTacticalPlayerController.h"

#include "AegisTacticalCameraActor.h"
#include "InputCoreTypes.h"

void AAegisTacticalPlayerController::SetupInputComponent()
{
    Super::SetupInputComponent();
    InputComponent->BindKey(EKeys::C, IE_Pressed, this,
        &AAegisTacticalPlayerController::CycleCameraPresentation);
}

void AAegisTacticalPlayerController::CycleCameraPresentation()
{
    if (AAegisTacticalCameraActor* Camera = Cast<AAegisTacticalCameraActor>(GetViewTarget()))
    {
        Camera->CyclePresentationMode();
    }
}
