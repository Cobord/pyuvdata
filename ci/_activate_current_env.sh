# This script should never be called directly, only sourced:

#     source _activate_current_env.sh

# Initialize the current shell
eval "$(`which micromamba` shell hook --shell=bash)"

# For robustness, try all possible activate commands.
conda activate "${ENV_NAME}" 2>/dev/null \
  || mamba activate "${ENV_NAME}" 2>/dev/null \
  || micromamba activate "${ENV_NAME}"
