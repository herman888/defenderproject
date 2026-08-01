"""
Cost-Per-Kill (CPK) Swarm Optimization Module for AEGIS / LARP.
Solves target allocation across multi-effector swarms (quadcopters vs micro-rockets vs EW)
by balancing Time-to-Intercept (TTI), probability of hit (Phit), and economic cost.
"""

import numpy as np
from scipy.optimize import linear_sum_assignment

class CostPerKillOptimizer:
    """
    Hungarian-based multi-effector optimal swarm allocator with CPK weighting.
    """

    def __init__(self, w_tti=0.4, w_phit=0.3, w_cpk=0.3):
        self.w_tti = w_tti
        self.w_phit = w_phit
        self.w_cpk = w_cpk

    def compute_assignment(self, effectors, threats):
        """
        Computes optimal 1-to-1 or N-to-M assignment matrix.
        
        effectors: list of dicts [{'id': 0, 'pos': [x,y,z], 'type': 'quad'|'rocket', 'speed': m/s, 'cost': $}]
        threats: list of dicts [{'id': 0, 'pos': [x,y,z], 'vel': [vx,vy,vz], 'priority': 1-10, 'value': $}]
        """
        num_eff = len(effectors)
        num_thr = len(threats)

        if num_eff == 0 or num_thr == 0:
            return []

        cost_matrix = np.zeros((num_eff, num_thr))

        for i, eff in enumerate(effectors):
            eff_pos = np.array(eff['pos'])
            eff_speed = eff.get('speed', 30.0)
            eff_cost = eff.get('cost', 500.0)
            eff_type = eff.get('type', 'quad')

            for j, thr in enumerate(threats):
                thr_pos = np.array(thr['pos'])
                thr_priority = thr.get('priority', 5.0)

                # 1. Time-to-Intercept (TTI)
                dist = np.linalg.norm(thr_pos - eff_pos)
                tti = dist / max(eff_speed, 1.0)

                # 2. Probability of Hit (Phit) estimate based on kinematic reachability
                thr_speed = np.linalg.norm(thr.get('vel', [0,0,0]))
                if eff_type == 'quad' and thr_speed > eff_speed * 1.1:
                    p_hit = 0.2  # Quadcopter cannot reliably catch faster target in tail chase
                else:
                    p_hit = min(0.95, max(0.5, 1.0 - (dist / 3000.0)))

                # 3. Cost-per-Kill Ratio (Dollars spent per threat neutralized)
                cpk_ratio = eff_cost / max(thr_priority * 1000.0, 1.0)

                # Combined Cost Function (Normalized)
                cost = (self.w_tti * (tti / 30.0) +
                        self.w_phit * (1.0 - p_hit) +
                        self.w_cpk * min(cpk_ratio, 2.0))

                cost_matrix[i, j] = cost

        # Solve optimal assignment via Hungarian Algorithm
        eff_indices, thr_indices = linear_sum_assignment(cost_matrix)

        assignments = []
        for e_idx, t_idx in zip(eff_indices, thr_indices):
            assignments.append({
                "effector_id": effectors[e_idx]['id'],
                "effector_type": effectors[e_idx].get('type', 'quad'),
                "threat_id": threats[t_idx]['id'],
                "assigned_cost": float(cost_matrix[e_idx, t_idx])
            })

        return assignments
