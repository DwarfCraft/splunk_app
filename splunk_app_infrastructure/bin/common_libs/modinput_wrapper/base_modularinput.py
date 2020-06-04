import sys
from os import path
lib_dir = path.dirname(path.dirname(path.abspath(__file__)))  # noqa
sys.path.append(lib_dir)  # noqa
sys.path.append(path.join(path.dirname(lib_dir), 'external_lib'))  # noqa

from solnlib.modular_input.modular_input import ModularInput
from rest_handler.session import session, authtoken_required


class BaseModularInput(ModularInput):
    """
    `BaseModularInput` class should have a subclass that implements its interface methods and
    those of the parent `ModularInput` class from `solnlib`. It sets the session token and inputs
    of the current process based on input metdata from splunk, and provides capabilities
    for custom setup and cleanup.
    """

    def __init__(self):
        super(BaseModularInput, self).__init__()
        self.inputs = {}

    def do_run(self, inputs):
        """
        Implements the abstract method defined by `ModularInput`. User should not modify this method
        directly and instead should implement the `do_execute` method.
        """
        self._additional_setup(inputs)
        self.do_execute()
        self._cleanup()

    @authtoken_required
    def do_execute(self):
        """
        Runs this modular input. To be implemented by subclass.
        """
        raise NotImplementedError()

    def do_additional_setup(self):
        """
        Optional setup method implemented by subclass. This method is called before `do_execute`
        """
        pass

    def do_cleanup(self):
        """
        Optional cleanup method implemented by subclass. This method is called after `do_execute`
        """
        pass

    def _additional_setup(self, inputs):
        if self.session_key:
            session.save(authtoken=self.session_key)
        self._parse_input_args(inputs)
        self.do_additional_setup()

    def _parse_input_args(self, inputs):
        for stanza_name, stanza_attr in inputs.items():
            inp_name = stanza_name.split('://')[1]
            self.inputs[inp_name] = stanza_attr

    def _cleanup(self):
        session.clear()
        self.do_cleanup()
