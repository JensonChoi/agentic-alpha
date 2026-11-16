# Optional OpenClaw client

Copy this directory into your OpenClaw installation's configured skills directory and reload its skills. Configure the Agentic Alpha URL reachable from that installation; localhost refers to the machine running the client. Supply API_TOKEN through the client's secret configuration if enabled. No OpenClaw gateway is required by the backend.

Try: “List my Agentic Alpha experiments”, “Compare the completed momentum and VOO simulations”, or “Explain the last recorded multi-agent proposal.”

The skill uses only HTTP simulation operations documented by the backend. Installation and compatibility with a particular OpenClaw release must be verified in that installation.

OpenClaw adds more value to recurring forward-simulation workflows than to backtesting. Backtests already run through the backend; OpenClaw provides a conversational way to launch them and inspect comparisons. Single-agent and multi-agent strategies, as well as forward simulation, work without OpenClaw using a configured inference provider.

For forward simulation, a scheduled OpenClaw automation could coordinate fresh-data acquisition, immutable dataset import, advancing an experiment, and reporting results. This workflow requires additional tools and configuration: the current skill does not implement data acquisition or experiment advancement. The backend worker checks for newly eligible completed sessions in the selected dataset, but does not fetch market data. A scheduled script can also coordinate these updates without OpenClaw. All execution remains simulated.

OpenClaw's current documentation describes heartbeat checks as ordinary scheduled automation jobs; consult the [heartbeat migration documentation](https://docs.openclaw.ai/gateway/heartbeat) for release-specific behavior.
