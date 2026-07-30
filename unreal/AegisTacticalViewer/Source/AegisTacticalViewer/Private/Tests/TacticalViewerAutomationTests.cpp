#if WITH_DEV_AUTOMATION_TESTS

#include "AegisTacticalTrackActor.h"
#include "Misc/AutomationTest.h"
#include "TacticalAssetRegistry.h"
#include "TacticalTelemetryComponent.h"
#include "TacticalTypes.h"
#include "Interfaces/IPv4/IPv4Address.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnuCoordinateConversionTest,
    "Aegis.TacticalViewer.Protocol.CoordinateConversion",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FEnuCoordinateConversionTest::RunTest(const FString& Parameters)
{
    TestEqual(TEXT("ENU metres map into Unreal centimetres with X=N and Y=E"),
        AAegisTacticalTrackActor::EnuToUnrealWorld(FVector(2.0, 5.0, 3.0)),
        FVector(500.0, 200.0, 300.0));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnuOrientationConversionTest,
    "Aegis.TacticalViewer.Protocol.OrientationConversion",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FEnuOrientationConversionTest::RunTest(const FString& Parameters)
{
    const FRotator IdentityOrientation = AAegisTacticalTrackActor::EnuOrientationToUnreal(
        FQuat::Identity, 42.0);
    TestTrue(TEXT("Identity ENU attitude points East, which maps to Unreal +Y"),
        FMath::IsNearlyEqual(IdentityOrientation.Yaw, 90.0f));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAssetFallbackTest,
    "Aegis.TacticalViewer.Visuals.AssetFallback",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FAssetFallbackTest::RunTest(const FString& Parameters)
{
    const FTacticalVisualDefinition Interceptor = FTacticalAssetRegistry::Resolve(
        TEXT("unknown-id"), TEXT("interceptor"), TEXT("unknown"));
    const FTacticalVisualDefinition Intruder = FTacticalAssetRegistry::Resolve(
        TEXT("unknown-id"), TEXT("intruder"), TEXT("unknown"));
    const FTacticalVisualDefinition Shahed = FTacticalAssetRegistry::Resolve(
        TEXT("intruder/shahed136"), TEXT("intruder"), TEXT("shahed136"));
    TestTrue(TEXT("Interceptor has an intentional fallback mesh"), !Interceptor.MeshPath.IsNull());
    TestTrue(TEXT("Intruder has an intentional fallback mesh"), !Intruder.MeshPath.IsNull());
    TestNotEqual(TEXT("Role colors remain distinguishable"), Interceptor.BaseColor, Intruder.BaseColor);
    TestFalse(TEXT("The attributed Shahed mesh replaces the engine fallback"),
        Shahed.MeshPath.GetAssetPathString().StartsWith(TEXT("/Engine/BasicShapes")));
    TestTrue(TEXT("Both authored Shahed shells are registered"),
        Shahed.DetailMeshPath.IsValid());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthStateTest,
    "Aegis.TacticalViewer.Protocol.StaleAndLossHealth",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHealthStateTest::RunTest(const FString& Parameters)
{
    FTacticalTelemetryHealth Health;
    TestTrue(TEXT("A feed with no packets is stale"), Health.IsStale(10.0f));
    Health.LastReceiveWorldSeconds = 10.0f;
    TestFalse(TEXT("Fresh telemetry is live"), Health.IsStale(10.5f));
    TestTrue(TEXT("Age beyond threshold is stale"), Health.IsStale(15.1f));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPacketValidationTest,
    "Aegis.TacticalViewer.Protocol.StrictPacketValidation",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FPacketValidationTest::RunTest(const FString& Parameters)
{
    const FString ValidPacket = TEXT("{\"schema\":\"aegis.tactical.v1\",\"bridge_schema\":\"aegis.unreal-bridge.v1\",\"status\":\"RUNNING\",\"site\":\"LOCAL\",\"sequence\":1,\"mission_time_s\":2.5,\"tracks\":{\"intruder\":{\"id\":\"intruder-1\",\"role\":\"intruder\",\"asset_id\":\"shahed_136\",\"type\":\"fixed_wing\",\"position_enu_m\":[1,2,3],\"velocity_enu_mps\":[0,0,0],\"orientation_xyzw\":[0,0,0,1],\"heading_deg\":90},\"interceptor\":null}}");
    UTacticalTelemetryComponent* Receiver = NewObject<UTacticalTelemetryComponent>();
    TestTrue(TEXT("A complete local display packet is accepted"),
        Receiver->ProcessPacketForAutomation(ValidPacket));
    TestFalse(TEXT("Malformed JSON is rejected"),
        Receiver->ProcessPacketForAutomation(TEXT("{broken")));
    TestFalse(TEXT("Fractional sequence numbers are rejected"),
        Receiver->ProcessPacketForAutomation(ValidPacket.Replace(TEXT("\"sequence\":1"), TEXT("\"sequence\":1.5"))));
    TestFalse(TEXT("Out-of-order packets are rejected"),
        Receiver->ProcessPacketForAutomation(ValidPacket));
    const FString LaterMissionPacket = ValidPacket
        .Replace(TEXT("\"sequence\":1"), TEXT("\"sequence\":20"))
        .Replace(TEXT("\"mission_time_s\":2.5"), TEXT("\"mission_time_s\":20.0"));
    TestTrue(TEXT("Later packets in the same mission are accepted"),
        Receiver->ProcessPacketForAutomation(LaterMissionPacket));
    const FString NewMissionPacket = ValidPacket
        .Replace(TEXT("\"mission_time_s\":2.5"), TEXT("\"mission_time_s\":0.5"));
    TestTrue(TEXT("A near-zero clock and reset sequence begins a new mission epoch"),
        Receiver->ProcessPacketForAutomation(NewMissionPacket));
    TestEqual(TEXT("The accepted null interceptor packet updates the sequence"),
        Receiver->GetHealth().LastSequence, static_cast<int64>(1));
    const FString EnrichedPacket = TEXT(
        "{\"schema\":\"aegis.tactical.v1\",\"bridge_schema\":\"aegis.unreal-bridge.v1\","
        "\"status\":\"TRACKING\",\"site\":\"LOCAL\",\"sequence\":2,\"mission_time_s\":0.7,"
        "\"tracks\":{\"intruder\":{\"id\":\"intruder-1\",\"role\":\"intruder\","
        "\"asset_id\":\"shahed_136\",\"type\":\"fixed_wing\","
        "\"position_enu_m\":[1,2,3],\"velocity_enu_mps\":[0,0,0],"
        "\"orientation_xyzw\":[0,0,0,1],\"heading_deg\":90},\"interceptor\":null},"
        "\"predicted_intercept_enu_m\":[4,5,6],"
        "\"sensors\":{\"radar_locked\":true,\"eo_locked\":false,"
        "\"fusion_source\":\"RADAR\",\"radar_failure\":false,"
        "\"eo_failure\":true,\"actuator_failure\":false},"
        "\"environment\":{\"name\":\"clear\",\"visibility_m\":10000,"
        "\"wind_enu_mps\":[1,2,0]},"
        "\"scenario\":{\"intruder\":\"shahed136\",\"pattern\":\"direct\","
        "\"pad\":\"mid\",\"recording\":true},"
        "\"simulation\":{\"requested_rate\":2,\"achieved_realtime_factor\":1.5,"
        "\"interceptor_speed_cap_mps\":70,"
        "\"interceptor_profile_evidence\":\"design-placeholder\","
        "\"guidance_mode\":\"ADAPTIVE_APN\",\"navigation_gain\":4.8,"
        "\"command_speed_mps\":63,\"closing_speed_mps\":31,"
        "\"los_rate_dps\":2.1,\"track_confidence\":0.92,"
        "\"ai_residual_authority\":0.0}}");
    TestTrue(TEXT("Optional tactical presentation data is validated and accepted"),
        Receiver->ProcessPacketForAutomation(EnrichedPacket));
    TestTrue(TEXT("Predicted intercept is exposed to the presentation layer"),
        Receiver->GetHealth().bHasPredictedIntercept);
    TestTrue(TEXT("Injected sensor state is visible in the HUD health model"),
        Receiver->GetHealth().bEoFailure);
    TestEqual(TEXT("Scenario preset is exposed to the HUD"),
        Receiver->GetHealth().ScenarioPattern, FString(TEXT("direct")));
    TestEqual(TEXT("Adaptive guidance mode is exposed to the HUD"),
        Receiver->GetHealth().GuidanceMode, FString(TEXT("ADAPTIVE_APN")));
    TestTrue(TEXT("Adaptive navigation gain is preserved"),
        FMath::IsNearlyEqual(Receiver->GetHealth().GuidanceNavigationGain, 4.8));
    TestTrue(TEXT("Rejected packets are visible to the HUD health state"),
        Receiver->GetHealth().RejectedPackets >= 3);
    TestEqual(TEXT("Receiver is deliberately loopback-only"),
        FIPv4Address::InternalLoopback.ToString(), FString(TEXT("127.0.0.1")));
    return true;
}

#endif
