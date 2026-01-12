import inspect
import logging
from typing import Any, Type, cast

from typing_extensions import Self  # type: ignore

from dunetuf.copy.dune.copy_dune import CopyDune

class CopyHomePro(CopyDune):
    """
    Concrete implementation of CopyDune for HomePro-based architecture.

    Currently, no additional logic is implemented.
    """

    def __new__(cls: Type[Self], *args: Any, **kwargs: Any) -> Self:
        """
        Create a new instance of CopyDune or its subclass.
        Returns:
            An instance of CopyHomePro or its subclass.
        """

        if cls is CopyHomePro:
            caller_frame = inspect.stack()[1]
            caller_module = inspect.getmodule(caller_frame[0])

            if caller_module is None or not (
                caller_module.__name__.startswith("dunetuf.copy.dune.copy_dune")
            ):
                raise RuntimeError(
                    "CopyHomePro (and its subclasses) can only be instantiated via CopyDune."
                )
            if "beam" in cls._product_name:
                from dunetuf.copy.dune.homepro.copy_beam import CopyBeam
                return cast(Self, CopyBeam(*args, **kwargs))
            else:
                return cast(Self, super().__new__(cls))

        return cast(Self, super().__new__(cls))