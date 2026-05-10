# Security and Privacy

## Trust Model

This project is designed for trusted local automation only.

- The bridge listens on `127.0.0.1` by default.
- The MCP server can execute Python inside the active Abaqus/CAE session.
- Do not expose the bridge to public or shared networks.

## Data That May Appear in Output

Depending on the commands you run, responses and logs may include:

- local file paths
- user names or home-directory paths embedded in your scripts
- model names, job names, and other Abaqus metadata

The repository itself does not collect telemetry. Logs are written to the system temp directory for local troubleshooting only.

## Before Sharing the Repository

Review the following before publishing or sharing the project:

1. Remove any personal paths from README examples and scripts.
2. Confirm temporary files, Abaqus output files, and virtual environments are excluded by `.gitignore`.
3. Avoid pasting command output that includes sensitive local paths into issues or discussions.