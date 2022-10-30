# packerpy

---

I built this module to help automate packer builds in python code. I found it to be nearly 
impossible to scale packer builds for a pipeline or automated environment without forking 
the code from packer's <code>golang</code> [implementation](https://github.com/hashicorp/packer).

The <code>PackerBuilder</code> I provide is extendable (as shown in <code>packerpy.examples.ami_builder</code>) 
in order to allow for a custom implementation of any packer builder plugin.

---

### Documentation

