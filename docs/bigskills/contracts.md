# BigSkills Contract Pattern

Use this pattern when a skill should behave like a reusable node in a larger system.

## Why contracts matter
A contract forces clarity. It makes the skill easier to compose, easier to debug, and easier to evaluate.

Without a contract, skills drift into vague "do some useful stuff" territory.

## Contract template

### Contract

#### Input
- **Required:** what the skill absolutely needs
- **Optional:** what improves output but is not mandatory
- **Format:** links, raw text, file path, brand voice file, JSON, etc.
- **Source:** where this usually comes from

#### Output
- **Produces:** the deliverable
- **Format:** inline markdown, saved file, JSON, doc, images, etc.
- **Default behavior:** what it returns if the user does not specify a format
- **Downstream use:** which other skills or workflows may consume it

#### Validation
- **Pre-conditions:** what must be true before running
- **Post-conditions:** what must be true after completion
- **Failure checks:** what to flag if the skill cannot produce a reliable result

## When to use a contract
Use one when:
- the skill sits in a pipeline
- the output feeds another skill
- the skill has quality requirements beyond “answer well”
- inputs are easy to misunderstand

## When a light contract is enough
Keep the contract brief when the skill is simple. The contract exists to clarify behavior, not to create ceremony.

## Example

### Contract

#### Input
- **Required:** one competitor ad URL
- **Optional:** target brand voice file, target platform
- **Format:** URL + optional file path
- **Source:** ad library research or previous workflow step

#### Output
- **Produces:** one structured breakdown and three adapted ad angles
- **Format:** inline markdown by default
- **Downstream use:** creative-copy-generator, image-prompt-builder

#### Validation
- **Pre-conditions:** ad URL must resolve, image must be readable
- **Post-conditions:** includes findings, angle summary, and adapted concepts
- **Failure checks:** do not invent image details if extraction failed
