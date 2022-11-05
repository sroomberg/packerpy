# packerpy

---

I built this module to help automate packer builds in python code. I found it to be nearly 
impossible to scale packer builds for a pipeline or automated environment without forking 
the code from packer's `golang` [implementation](https://github.com/hashicorp/packer).

---

### Requirements

- [Install Packer](https://developer.hashicorp.com/packer/downloads)

### Installation

`pip install PackerBuilder` ([PyPi](https://pypi.org/project/PackerBuilder/1.0.0/))


### Documentation

[`PackerBuilder`](./src/builder.py): This class is extendable (as shown in 
[`packerpy.examples.ami_builder`](./examples/ami_builder.py)) in order to allow for a custom implementation 
of any packer builder plugin. The `PackerBuilder` will generate a json packer configuration file that can 
be executed by the packer cli.

[`PackerClient`](./src/client.py): This is a utility class built to interact with the packer cli.

[`models`](./src/models.py): The `models` submodule contains objects that map to packer config blocks in the 
`.pkr.json` file that gets generated.
