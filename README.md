# Spyglass Scout-Spotter SDK

The core substrate for swarm scouting agents to `spot`, `bid`, `claim`, and `report`.

## Features
- **Canonical Primitive**: `Spotting` dataclass (protobuf-ready).
- **Substrate-Agnostic**: Writes to pheromone logs or pushes to event buses.
- **FCFS Bidding**: Basic conflict resolution via `SpottingBoard`.
- **Integrity**: Placeholder hooks for WaveLang-style command validation via `CommandGuard`.

## Usage
```python
from sdk.spyglass_sdk import Spotting, Scout, PheromoneSink
sink = PheromoneSink()
scout = Scout("my-agent", sink)
scout.spot("scout_event", "target_path", {"info": "found something"})
```
