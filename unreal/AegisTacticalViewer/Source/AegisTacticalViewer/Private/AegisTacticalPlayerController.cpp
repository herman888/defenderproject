#include "AegisTacticalPlayerController.h"

#include "AegisTacticalCameraActor.h"
#include "AegisTacticalHUD.h"
#include "Common/UdpSocketBuilder.h"
#include "InputCoreTypes.h"
#include "Interfaces/IPv4/IPv4Address.h"
#include "SocketSubsystem.h"
#include "Sockets.h"

void AAegisTacticalPlayerController::SetupInputComponent()
{
    Super::SetupInputComponent();
    InputComponent->BindKey(EKeys::C, IE_Pressed, this,
        &AAegisTacticalPlayerController::CycleCameraPresentation);
    InputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this,
        &AAegisTacticalPlayerController::ToggleSimulationPause);
    InputComponent->BindKey(EKeys::R, IE_Pressed, this,
        &AAegisTacticalPlayerController::RestartSimulation);
    InputComponent->BindKey(EKeys::One, IE_Pressed, this,
        &AAegisTacticalPlayerController::SetSimulationRate1x);
    InputComponent->BindKey(EKeys::Two, IE_Pressed, this,
        &AAegisTacticalPlayerController::SetSimulationRate2x);
    InputComponent->BindKey(EKeys::Four, IE_Pressed, this,
        &AAegisTacticalPlayerController::SetSimulationRate4x);
    InputComponent->BindKey(EKeys::Eight, IE_Pressed, this,
        &AAegisTacticalPlayerController::SetSimulationRate8x);
    InputComponent->BindKey(EKeys::F5, IE_Pressed, this,
        &AAegisTacticalPlayerController::ToggleRadarFailure);
    InputComponent->BindKey(EKeys::F6, IE_Pressed, this,
        &AAegisTacticalPlayerController::ToggleEoFailure);
    InputComponent->BindKey(EKeys::F7, IE_Pressed, this,
        &AAegisTacticalPlayerController::ToggleActuatorFailure);
    InputComponent->BindKey(EKeys::X, IE_Pressed, this,
        &AAegisTacticalPlayerController::ClearFailures);
    InputComponent->BindKey(EKeys::N, IE_Pressed, this,
        &AAegisTacticalPlayerController::NextScenarioPreset);
    InputComponent->BindKey(EKeys::H, IE_Pressed, this,
        &AAegisTacticalPlayerController::ToggleHudMode);
    InputComponent->BindAxis(TEXT("MouseX"), this,
        &AAegisTacticalPlayerController::OrbitYaw);
    InputComponent->BindAxis(TEXT("MouseY"), this,
        &AAegisTacticalPlayerController::OrbitPitch);
    InputComponent->BindAxis(TEXT("MouseWheelAxis"), this,
        &AAegisTacticalPlayerController::OrbitZoom);
    InputComponent->BindAxis(TEXT("Gamepad_RightX"), this,
        &AAegisTacticalPlayerController::OrbitYaw);
    InputComponent->BindAxis(TEXT("Gamepad_RightY"), this,
        &AAegisTacticalPlayerController::OrbitPitch);
}

void AAegisTacticalPlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (ControlSocket != nullptr)
    {
        ControlSocket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ControlSocket);
        ControlSocket = nullptr;
    }
    Super::EndPlay(EndPlayReason);
}

void AAegisTacticalPlayerController::CycleCameraPresentation()
{
    if (AAegisTacticalCameraActor* Camera = Cast<AAegisTacticalCameraActor>(GetViewTarget()))
    {
        Camera->CyclePresentationMode();
    }
}

void AAegisTacticalPlayerController::ToggleSimulationPause()
{
    SendLocalSimulationCommand(TEXT("{\"schema\":\"aegis.local-sim-control.v1\",\"action\":\"pause_toggle\"}"),
        TEXT("LOCAL SIM: PAUSE/RESUME REQUESTED"));
}

void AAegisTacticalPlayerController::RestartSimulation()
{
    SendLocalSimulationCommand(TEXT("{\"schema\":\"aegis.local-sim-control.v1\",\"action\":\"restart\"}"),
        TEXT("LOCAL SIM: RESTART REQUESTED"));
}

void AAegisTacticalPlayerController::SetSimulationRate1x() { SetSimulationRate(1.0); }
void AAegisTacticalPlayerController::SetSimulationRate2x() { SetSimulationRate(2.0); }
void AAegisTacticalPlayerController::SetSimulationRate4x() { SetSimulationRate(4.0); }
void AAegisTacticalPlayerController::SetSimulationRate8x() { SetSimulationRate(8.0); }

void AAegisTacticalPlayerController::ToggleRadarFailure()
{
    ToggleFailure(TEXT("radar"), TEXT("RADAR FAILURE TOGGLED"));
}

void AAegisTacticalPlayerController::ToggleEoFailure()
{
    ToggleFailure(TEXT("eo"), TEXT("EO FAILURE TOGGLED"));
}

void AAegisTacticalPlayerController::ToggleActuatorFailure()
{
    ToggleFailure(TEXT("actuator"), TEXT("ACTUATOR FAILURE TOGGLED"));
}

void AAegisTacticalPlayerController::ClearFailures()
{
    SendLocalSimulationCommand(
        TEXT("{\"schema\":\"aegis.local-sim-control.v1\",\"action\":\"clear_failures\"}"),
        TEXT("LOCAL SIM: ALL FAILURES CLEARED"));
}

void AAegisTacticalPlayerController::NextScenarioPreset()
{
    SendLocalSimulationCommand(
        TEXT("{\"schema\":\"aegis.local-sim-control.v1\",\"action\":\"next_preset\"}"),
        TEXT("LOCAL SIM: LOADING NEXT SCENARIO PRESET"));
}

void AAegisTacticalPlayerController::ToggleHudMode()
{
    if (AAegisTacticalHUD* Hud = Cast<AAegisTacticalHUD>(GetHUD()))
    {
        Hud->TogglePresentationMode();
        LastLocalCommand = Hud->IsCleanCinematicMode()
            ? TEXT("DISPLAY: CLEAN CINEMATIC HUD")
            : TEXT("DISPLAY: FULL TACTICAL HUD");
    }
}

void AAegisTacticalPlayerController::OrbitYaw(const float Value)
{
    if (AAegisTacticalCameraActor* Camera = Cast<AAegisTacticalCameraActor>(GetViewTarget()))
    {
        Camera->AddOrbitYaw(Value);
    }
}

void AAegisTacticalPlayerController::OrbitPitch(const float Value)
{
    if (AAegisTacticalCameraActor* Camera = Cast<AAegisTacticalCameraActor>(GetViewTarget()))
    {
        Camera->AddOrbitPitch(-Value);
    }
}

void AAegisTacticalPlayerController::OrbitZoom(const float Value)
{
    if (AAegisTacticalCameraActor* Camera = Cast<AAegisTacticalCameraActor>(GetViewTarget()))
    {
        Camera->AddOrbitZoom(Value);
    }
}

void AAegisTacticalPlayerController::SetSimulationRate(const double Rate)
{
    SendLocalSimulationCommand(FString::Printf(
        TEXT("{\"schema\":\"aegis.local-sim-control.v1\",\"action\":\"set_speed\",\"speed\":%.1f}"), Rate),
        FString::Printf(TEXT("LOCAL SIM: %.0fx REQUESTED"), Rate));
}

void AAegisTacticalPlayerController::ToggleFailure(
    const FString& Failure, const FString& Label)
{
    SendLocalSimulationCommand(FString::Printf(
        TEXT("{\"schema\":\"aegis.local-sim-control.v1\",\"action\":\"toggle_failure\",\"failure\":\"%s\"}"),
        *Failure), FString::Printf(TEXT("LOCAL SIM: %s"), *Label));
}

void AAegisTacticalPlayerController::SendLocalSimulationCommand(
    const FString& Json, const FString& Label)
{
    if (ControlSocket == nullptr)
    {
        ControlSocket = FUdpSocketBuilder(TEXT("AegisLocalSimulationControls"))
            .AsNonBlocking()
            .AsReusable();
    }
    bool bValidAddress = false;
    TSharedRef<FInternetAddr> Endpoint = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->CreateInternetAddr();
    Endpoint->SetIp(TEXT("127.0.0.1"), bValidAddress);
    Endpoint->SetPort(8789);
    int32 BytesSent = 0;
    FTCHARToUTF8 Payload(*Json);
    if (ControlSocket != nullptr && bValidAddress
        && ControlSocket->SendTo(reinterpret_cast<const uint8*>(Payload.Get()), Payload.Length(), BytesSent, *Endpoint))
    {
        LastLocalCommand = Label;
    }
    else
    {
        LastLocalCommand = TEXT("LOCAL SIM CONTROL OFFLINE — START THE DEMO LAUNCHER");
    }
}
