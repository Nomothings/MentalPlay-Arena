# K-SADS Module

This directory contains the Kiddie Schedule for Affective Disorders and Schizophrenia (K-SADS) assessment module for the MentalPlay Quizzer system.

## Module Structure

```
K-SADS-module/
├── config.yaml          # Module-specific configuration
├── inquiries.json       # K-SADS questions database
├── rules.json           # K-SADS rules database
└── README.md            # This file
```

## Files Description

### config.yaml
Module-specific configuration file containing:
- Scoring rules and thresholds
- Logging settings
- Answer format configuration

### inquiries.json
Complete K-SADS questions database in JSON format, including:
- Question IDs
- Question text
- Answer spaces
- Categories and domains
- Jump actions

### rules.json
K-SADS assessment rules in JSON format, including:
- Rule expressions
- Category mappings
- Score assignments
- Action directives

## Usage

To use this module with the MentalPlay Quizzer:

1. Ensure the module directory is located in the `MentalPlay/Quizzer/` directory
2. Run the Quizzer with the `--module K-SADS` parameter
3. The Quizzer will automatically load the module's `inquiries.json` and `rules.json` files

## Adding New Questions

Refer to the main `ADD_NEW_QUESTIONS_GUIDE.md` in the parent directory for instructions on how to add new questions to the K-SADS module.

## Data Storage

Data for this module is stored in:
- Database: `MentalPlay/data/K-SADS/ksads.db`
- Answers: `MentalPlay/data/K-SADS/answers/`

## License

[Add appropriate license information here]