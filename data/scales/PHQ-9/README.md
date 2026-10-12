# PHQ-9 Module

## Overview

The PHQ-9 (Patient Health Questionnaire-9) is a widely used screening and assessment tool for depression. This module implements the PHQ-9 scale within the MentalPlay framework, allowing for automated administration, scoring, and result interpretation.

## PHQ-9 Scale Description

The PHQ-9 consists of 9 items that correspond to the Diagnostic and Statistical Manual of Mental Disorders (DSM-5) criteria for major depressive disorder. Each item asks about the frequency of symptoms over the past two weeks, with response options ranging from "Not at all" (0 points) to "Nearly every day" (3 points).

## Module Structure

This module contains the following files:

- `inquiries.json`: Contains the 9 PHQ-9 questions phrased from a doctor's perspective in English
- `rules.json`: Defines the scoring logic for the PHQ-9 scale
- `config.yaml`: Module-specific configuration settings
- `README.md`: This file, providing information about the module

## Scoring System

### Item Scoring
Each of the 9 items is scored as follows:
- Not at all: 0 points
- Several days: 1 point
- More than half the days: 2 points
- Nearly every day: 3 points

### Total Score Interpretation
The total score ranges from 0 to 27, with the following interpretations:
- 0-4: No depressive symptoms
- 5-9: Mild depression
- 10-14: Moderate depression
- 15-19: Moderately severe depression
- 20-27: Severe depression

## Usage

To use the PHQ-9 module with the MentalPlay framework, specify "PHQ-9" as the module when initializing the Quizzer class.

### Example
```python
from Quizzer.core.quizzer import Quizzer

# Initialize the quizzer with the PHQ-9 module
quizzer = Quizzer(module="PHQ-9")

# Start a new test
test_number, first_question = quizzer.start_new_test("Test User")

# Continue with the assessment process...
```

## Data Storage

- Responses are stored in the database specified in the configuration
- Results are exported in JSON format by default
- All interactions and scores are preserved for later analysis

## References

1. Kroenke K, Spitzer RL, Williams JB. The PHQ-9: validity of a brief depression severity measure. J Gen Intern Med. 2001;16(9):606-613.
2. American Psychiatric Association. (2013). Diagnostic and statistical manual of mental disorders (5th ed.). Arlington, VA: American Psychiatric Publishing.
