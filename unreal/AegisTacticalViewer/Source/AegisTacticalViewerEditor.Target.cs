using UnrealBuildTool;
using System.Collections.Generic;

public class AegisTacticalViewerEditorTarget : TargetRules
{
    public AegisTacticalViewerEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.AddRange(new string[] { "AegisTacticalViewer" });
    }
}
