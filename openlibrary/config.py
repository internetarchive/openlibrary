import yaml

runtime_config = {}

def load(config_file):
    global runtime_config
    runtime_config = yaml.load(open(config_file))
