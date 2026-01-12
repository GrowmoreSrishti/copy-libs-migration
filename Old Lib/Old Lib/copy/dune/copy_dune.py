import inspect
from typing import Any, Type, cast

from typing_extensions import Self  # type: ignore

from dunetuf.copy.copy import Copy


class CopyDune(Copy):
    """
    Concrete implementation of Copy for Dune-based architecture.
    """

    def __new__(cls: Type[Self], *args: Any, **kwargs: Any) -> Self:
        """
        Create a new instance of CopyDune or its subclass.
        Returns:
            An instance of CopyDune or its subclass.
        """
        # Verify that instantiation is coming from 'Copy'
        caller_frame = inspect.stack()[1]
        caller_module = inspect.getmodule(caller_frame[0])
        if caller_module is None or not (
            caller_module.__name__.startswith("dunetuf.copy.copy")
        ):
            raise RuntimeError(
                "CopyDune (and its subclasses) can only be instantiated via Copy."
            )

        if cls is CopyDune:
            if cls._family_name == "enterprise":
                from dunetuf.copy.dune.enterprise.copy_enterprise import \
                    CopyEnterprise

                cls = cast(Type[Self], CopyEnterprise)
            elif cls._family_name == "designjet":
                from dunetuf.copy.dune.designjet.copy_designjet import \
                    CopyDesignJet

                cls = cast(Type[Self], CopyDesignJet)
            elif cls._family_name == "homepro":
                from dunetuf.copy.dune.homepro.copy_homepro import CopyHomePro

                cls = cast(Type[Self], CopyHomePro)
            else:
                # Fall back to CopyDune for unsupported family names
                return cast(Self, super().__new__(cls))

        return cast(Self, super().__new__(cls))
