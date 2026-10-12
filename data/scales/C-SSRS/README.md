# C-SSRS Module for MentalPlay Framework

## Overview

The C-SSRS (Columbia-Suicide Severity Rating Scale) module is an implementation of the standardized suicide risk assessment tool within the MentalPlay framework. This module enables automated administration, scoring, and result interpretation of the C-SSRS scale using LLM-powered question-answering.

## C-SSRS Scale Description

The Columbia-Suicide Severity Rating Scale (C-SSRS) is a structured interview designed to assess suicide risk in individuals. It evaluates both suicidal ideation and suicidal behavior, with a focus on:

- **Suicidal Ideation**: Passive and active thoughts about death and suicide
- **Suicidal Behavior**: Actual attempts, aborted attempts, and preparatory acts

### Key Features

- **6-Level Risk Classification**: From "No Suicidal Ideation" (Level 1) to "Suicidal Behavior" (Level 6)
- **Time-Based Assessment**: Focuses on the past 1 month for ideation and past 3 months/4 weeks for behavior
- **Yes/No Response Format**: Simple, clear response options
- **Skip Logic**: Efficient administration by skipping irrelevant questions

## Module Structure

```
C-SSRS-module/
├── inquiries.json       # English, doctor-perspective questions
├── rules.json           # C-SSRS scoring rules and logic
├── config.yaml          # Module-specific configuration
└── README.md            # This documentation
```

## File Descriptions

### inquiries.json

Contains 7 structured questions in English, designed from a doctor's perspective to assess suicide risk in adolescents. Questions are organized into two main categories:

1. **Suicidal Ideation** (5 questions)
2. **Suicidal Behavior** (2 questions)

Each question includes:
- `question_id`: Unique identifier
- `question_text`: Doctor-perspective English question
- `domain`: Broad assessment area
- `category`: Specific assessment category
- `category_id`: Numeric category identifier
- `answer_space`: Valid response options (Yes/No)
- `action`: Next question or action to take

### rules.json

Defines the scoring and jump logic based on C-SSRS guidelines:

- **Skip Logic**: Automatically jumps to suicide behavior questions if no active suicidal ideation
- **Risk Level Scoring**: Maps responses to 6 risk levels (1-6)
- **Rule Evaluation**: Uses logical expressions to determine risk level

### config.yaml

Module-specific configuration settings:

- **Scoring Configuration**: Special categories and jump questions
- **Logging Configuration**: Log level, file path, and console output
- **Answer Configuration**: Save format for responses

## Scoring System

The C-SSRS uses a **highest severity** scoring approach, where the final risk level is determined by the most severe response:

| Level | Risk Classification | Criteria |
|-------|---------------------|----------|
| 1 | No Suicidal Ideation (Lowest Risk) | Q1 = No and Q2 = No |
| 2 | Passive Suicidal Ideation (Mild Risk) | Q1 = Yes and Q2 = No |
| 3 | Active Suicidal Ideation (No Specific Method) (Moderate Risk) | Q2 = Yes and Q3 = No |
| 4 | Suicidal Method Conception (Moderate-Severe Risk) | Q3 = Yes and Q4 = No |
| 5 | Plan But No Action (Severe Risk) | Q4 = Yes or Q5 = Yes |
| 6 | Suicidal Behavior (Extreme Risk) | Q6A = Yes or Q6B = Yes |

## Usage

### Integration with MentalPlay Framework

The C-SSRS module integrates seamlessly with the MentalPlay Quizzer framework:

1. **Initialization**: Create a Quizzer instance with `module="C-SSRS"`
2. **Start Test**: Begin a new test with a subject name
3. **Question Flow**: Answer questions sequentially as they appear
4. **Result Generation**: Get risk level score and detailed report

### Example Usage

```python
from Quizzer.core.quizzer import Quizzer

# Initialize the C-SSRS quizzer
quizzer = Quizzer(module="C-SSRS")

# Start a new test
test_number, first_question = quizzer.start_new_test("Test Subject")

# Answer questions (example)
next_question = quizzer.submit_answer(first_question["question_id"], "No")
# Continue answering until test completes

# Get results
scores = quizzer.get_current_scores()
report = quizzer.generate_report()
```

## Data Storage

All test data is stored in an SQLite database specific to the C-SSRS module:

- **Answers**: Raw and mapped responses
- **Scores**: Calculated risk levels
- **Test Metadata**: Test number, subject name, timestamps

## Testing

To test the C-SSRS module:

1. Navigate to the tests directory: `cd tests/`
2. Run the test script: `python test_C-SSRS.py --test-type three-patients`
3. Review the output and generated reports

### Test Types

- **single**: Test with a single patient
- **three-patients**: Test with three different answer strategies (first option, last option, random)

## Configuration Options

### Logging

- `level`: Log verbosity (DEBUG, INFO, WARNING, ERROR)
- `file`: Path to log file
- `console`: Whether to output logs to console

### Scoring

- `special_categories`: List of category IDs requiring special handling
- `special_jump_question`: Default question to jump to for special cases

### Answers

- `format`: Format for saving answers (json, csv, excel)

## Requirements

- Python 3.8+
- MentalPlay framework dependencies
- LLM service configuration

## Development Guidelines

When modifying the C-SSRS module:

1. Maintain consistency with the original C-SSRS scale
2. Follow the existing file structure and formatting
3. Test thoroughly with all risk level scenarios
4. Update documentation for any changes

## References

- Columbia-Suicide Severity Rating Scale (C-SSRS): https://cssrs.columbia.edu/
- C-SSRS Administration Guidelines
- MentalPlay Framework Documentation

## License

This module is part of the MentalPlay framework and follows the same licensing terms.
