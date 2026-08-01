"""Multi-effector swarm defense scenarios."""

from scenarios import INTRUDER_TYPES, ATTACK_PATTERNS, PAD_OFFSETS

MULTI_EFFECTOR_SCENARIOS = {
    'saturation_6v3': {
        'threats': [
            {'type': 'shahed136', 'pattern': 'direct'},
            {'type': 'shahed136', 'pattern': 'nap_earth'},
            {'type': 'fpv_attack', 'pattern': 'spiral'},
            {'type': 'fpv_attack', 'pattern': 'crossing'},
            {'type': 'consumer_quad', 'pattern': 'pop_up'},
            {'type': 'consumer_quad', 'pattern': 'offset'},
        ],
        'interceptors': [
            {'type': 'quad'},
            {'type': 'quad'},
            {'type': 'quad'},
            {'type': 'rocket'},
            {'type': 'rocket'},
        ],
        'description': '6 mixed threats (2x shahed, 2x fpv, 2x consumer) vs 3 quad interceptors + 2 micro-rockets',
    },
    'pincer_attack': {
        'threats': [
            {'type': 'fpv_attack', 'pattern': 'direct'},
            {'type': 'fpv_attack', 'pattern': 'direct'},
            {'type': 'fpv_attack', 'pattern': 'direct'},
            {'type': 'fpv_attack', 'pattern': 'direct'},
        ],
        'interceptors': [
            {'type': 'quad'},
            {'type': 'quad'},
            {'type': 'quad'},
            {'type': 'quad'},
            {'type': 'rocket'},
        ],
        'description': '4 threats from 2 opposing bearings (180° split) vs 4 quads + 1 rocket',
    },
    'overwhelm_8v2': {
        'threats': [
            {'type': 'fpv_attack', 'pattern': 'direct'},
            {'type': 'fpv_attack', 'pattern': 'direct'},
            {'type': 'fpv_attack', 'pattern': 'spiral'},
            {'type': 'fpv_attack', 'pattern': 'spiral'},
            {'type': 'fpv_attack', 'pattern': 'crossing'},
            {'type': 'fpv_attack', 'pattern': 'crossing'},
            {'type': 'fpv_attack', 'pattern': 'offset'},
            {'type': 'fpv_attack', 'pattern': 'offset'},
        ],
        'interceptors': [
            {'type': 'quad'},
            {'type': 'quad'},
            {'type': 'rocket'},
            {'type': 'rocket'},
            {'type': 'rocket'},
            {'type': 'rocket'},
        ],
        'description': '8 fpv threats vs 2 quads + 4 rockets (stress test)',
    },
    'decoy_swarm': {
        'threats': [
            {'type': 'consumer_quad', 'pattern': 'direct'},
            {'type': 'consumer_quad', 'pattern': 'direct'},
            {'type': 'consumer_quad', 'pattern': 'direct'},
            {'type': 'shahed136', 'pattern': 'nap_earth'},
        ],
        'interceptors': [
            {'type': 'quad'},
            {'type': 'quad'},
            {'type': 'rocket'},
            {'type': 'rocket'},
        ],
        'description': '3 decoy consumer drones + 1 high-value shahed vs 2 quads + 2 rockets',
    }
}

def build_multi_effector_mission(scenario_name: str) -> dict:
    """
    Returns the scenario dictionary for the given scenario name.
    
    Args:
        scenario_name (str): The name of the scenario.
        
    Returns:
        dict: The scenario configuration.
        
    Raises:
        KeyError: If the scenario_name is not found.
    """
    if scenario_name not in MULTI_EFFECTOR_SCENARIOS:
        raise KeyError(f"Unknown scenario: {scenario_name}")
    return MULTI_EFFECTOR_SCENARIOS[scenario_name]
