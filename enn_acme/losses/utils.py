# Copyright 2022 DeepMind Technologies Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or  implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Helpful functions relating to losses."""
import dataclasses
from typing import Callable, Optional, Tuple, Sequence

import chex
from enn import losses as enn_losses
from enn import networks
from enn_acme import base as agent_base
import haiku as hk
import reverb


def add_l2_weight_decay(
    loss_fn: agent_base.LossFn,
    scale_fn: Callable[[int], float],  # Maps learner_steps --> l2 decay
    predicate: Optional[enn_losses.PredicateFn] = None,
) -> agent_base.LossFn:
  """Adds l2 weight decay to a given loss function."""
  def new_loss(
      enn: networks.EnnNoState,
      params: hk.Params,
      state: agent_base.LearnerState,
      batch: reverb.ReplaySample,
      key: chex.PRNGKey,
  ) -> Tuple[chex.Array, agent_base.LossMetrics]:
    loss, metrics = loss_fn(enn, params, state, batch, key)
    l2_penalty = enn_losses.l2_weights_with_predicate(params, predicate)
    decay = l2_penalty * scale_fn(state.learner_steps)
    total_loss = loss + decay
    metrics['decay'] = decay
    metrics['raw_loss'] = loss
    return total_loss, metrics
  return new_loss


@dataclasses.dataclass
class CombineLossConfig:
  loss_fn: agent_base.LossFn
  name: str = 'unnamed'  # Name for the loss function
  weight: float = 1.  # Weight to scale the loss by


def combine_losses(losses: Sequence[CombineLossConfig]) -> agent_base.LossFn:
  """Combines multiple losses into a single loss."""

  def loss_fn(enn: networks.EnnNoState,
              params: hk.Params,
              state: agent_base.LearnerState,
              batch: reverb.ReplaySample,
              key: chex.PRNGKey) -> Tuple[chex.Array, agent_base.LossMetrics]:
    combined_loss = 0.
    combined_metrics = {}
    for loss_config in losses:
      loss, metrics = loss_config.loss_fn(enn, params, state, batch, key)
      combined_metrics[f'{loss_config.name}:loss'] = loss
      for name, value in metrics.items():
        combined_metrics[f'{loss_config.name}:{name}'] = value
      combined_loss += loss_config.weight * loss
    return combined_loss, combined_metrics

  return loss_fn

