using UnrealBuildTool;

public class AegisTacticalViewer : ModuleRules
{
    public AegisTacticalViewer(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core", "CoreUObject", "Engine", "InputCore"
        });

        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "Json", "JsonUtilities", "Networking", "Sockets"
        });
    }
}
