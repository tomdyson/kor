"""Definitions of input elements."""
import abc
import dataclasses
import re
from typing import Optional, Sequence

# For now, limit what's allowed for identifiers.
# The main constraints
# 1) Relying on HTML parser to parse output
# 2) One of the type descriptors is TypeScript, so we want to produce valid TypeScript identifiers.
# We can lift the constraints later if it becomes important, not worth the effort for a v0.
VALID_IDENTIFIER_PATTERN = re.compile(r"^[a-z_][0-9a-z_]*$")


def _write_single_tag(tag_name: str, data: str) -> str:
    """Write a tag."""
    return f"<{tag_name}>{data}</{tag_name}>"


def _write_tag(tag_name: str, data_values: str | Sequence[str]) -> str:
    """Write a tag."""
    if isinstance(data_values, str):
        data_values = [data_values]

    return "".join(_write_single_tag(tag_name, value) for value in data_values)


def _write_complex_tag(tag_name: str, data: dict[str, str]) -> str:
    """Write a complex tag."""
    s_data = "".join(
        [
            _write_tag(key, value)
            for key, value in sorted(data.items(), key=lambda item: item[0])
        ]
    )
    return _write_tag(tag_name, s_data)


@dataclasses.dataclass(frozen=True, kw_only=True)
class AbstractInput(abc.ABC):
    """Abstract input element.

    Each input is expected to have a unique ID, and should
    only use alphanumeric characters.

    The ID should be unique across all inputs that belong
    to a given form.

    The description should describe what the input is about.
    """

    id: str  # Unique ID
    description: str = ""
    multiple: bool = False
    custom_type_name: Optional[str] = None
    #
    # @property
    # def input_full_description(self) -> str:
    #     """A full description for the input."""
    #     return f"<{self.id}>: {self.type_name} # {self.description}"

    @property
    def type_name(self) -> str:
        """Default implementation of a type name is just the class name with the `Input` removed.

        Please note that this behavior will likely change.
        """
        class_name = self.__class__.__name__

        if self.multiple:
            class_name = f"Multiple {class_name}"

        if class_name.endswith("Input"):
            return class_name.removesuffix("Input")
        return class_name

    def __post_init__(self) -> None:
        """Post initialization hook."""
        if not VALID_IDENTIFIER_PATTERN.match(self.id):
            raise ValueError(
                f"`{self.id}` is not a valid identifier. "
                f"Please only use lower cased a-z, _ or the digits 0-9"
            )


@dataclasses.dataclass(frozen=True, kw_only=True)
class ExtractionInput(AbstractInput, abc.ABC):
    """An abstract definition for inputs that involve extraction.

    An extraction input can be associated with 2 different types of examples:

    1) extraction examples (called simply `examples`)
    2) null examples (called `null_examples`)

    ## Extraction examples

    A standard extraction example is a 2-tuple composed of a text segment and the expected
    extraction.

    For example:
        [
            ("I bought this cookie for $10", "$10"),
            ("Eggs cost twelve dollars", "twelve dollars"),
        ]

    ## Null examples

    Null examples are segments of text for which nothing should be extracted.
    Good null examples will likely be challenging, adversarial examples.

    For example:
        for an extraction input about company names nothing should be extracted
        from the text: "I eat an apple every day.".
    """

    examples: Sequence[tuple[str, str | list[str]]]

    @property
    def llm_examples(self) -> list[tuple[str, str]]:
        """List of 2-tuples of input, output.

        Does not include the `Input: ` or `Output: ` prefix
        """
        formatted_examples = []
        for text, extraction in self.examples:
            if isinstance(extraction, str) and not extraction.strip():
                value = ""
            else:
                value = _write_tag(self.id, extraction)
            formatted_examples.append((text, value))
        return formatted_examples


@dataclasses.dataclass(frozen=True, kw_only=True)
class ObjectInput(AbstractInput, abc.ABC):
    """An abstract definition for an input that involves capturing a complex object.

    TODO(Eugene): Maybe this should also be a form?
    """

    examples: Sequence[tuple[str, dict[str, str | list[str]]]]

    @property
    def llm_examples(self) -> list[tuple[str, str]]:
        """List of 2-tuples of input, output.

        Does not include the `Input: ` or `Output: ` prefix
        """
        formatted_examples = []
        for text, extraction in self.examples:
            formatted_examples.append((text, _write_complex_tag(self.id, extraction)))

        return formatted_examples


@dataclasses.dataclass(frozen=True, kw_only=True)
class DateInput(ExtractionInput):
    """Built-in date input."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class Number(ExtractionInput):
    """Built-in number input."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class TimePeriod(ExtractionInput):
    """Built-in for more general time-periods; e.g., 'after dinner', 'next year'"""


@dataclasses.dataclass(frozen=True, kw_only=True)
class NumericRange(ExtractionInput):
    """Built-in numeric range input."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class TextInput(ExtractionInput):
    """Built-in text input."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class Option(AbstractInput):
    """Built-in option input must be part of a selection input."""

    examples: Sequence[str]


@dataclasses.dataclass(frozen=True, kw_only=True)
class Selection(AbstractInput):
    """Built-in selection input.

    A selection input is composed of one or more options.
    """

    options: Sequence[Option]
    # If multiple=true, selection input allows for multiple options to be selected.
    null_examples: Sequence[str] = tuple()
    multiple: bool = False

    @property
    def llm_examples(self) -> list[tuple[str, str]]:
        """Examples ready for llm-consumption."""
        formatted_examples = []
        for option in self.options:
            for example in option.examples:
                formatted_examples.append((example, _write_tag(self.id, option.id)))

        for null_example in self.null_examples:
            formatted_examples.append((null_example, ""))

        return formatted_examples

    @property
    def option_ids(self) -> list[str]:
        """Get a list of the option ids."""
        return sorted(option.id for option in self.options)

    @property
    def type_name(self) -> str:
        """Over-ride type name to provide special behavior."""
        options_string = ",".join(self.option_ids)
        if self.multiple:
            formatted_type = f"Multiple Select[{options_string}]"
        else:
            formatted_type = f"Select[{options_string}]"
        return formatted_type


@dataclasses.dataclass(frozen=True, kw_only=True)
class Form(ExtractionInput):
    """A form encapsulated a collection of inputs.

    The form should have a good description of the context in which the data is collected.
    """

    elements: Sequence[ExtractionInput]
