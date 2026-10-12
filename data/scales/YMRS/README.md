# Young Mania Rating Scale (YMRS) Module

## Overview

The YMRS (Young Mania Rating Scale) module is designed to assess the severity of manic symptoms in adolescents and adults. It consists of 11 items that evaluate various aspects of mania, including mood elevation, activity level, sleep patterns, and thought processes.

## Module Structure

```
YMRS-module/
├── inquiries.json      # English version of doctor's questions
├── rules.json          # Scoring rules based on YMRS scale
├── config.yaml         # YMRS environment configuration
├── scoring.py          # Severity grading method
└── README.md           # YMRS module description
```

## YMRS Scale Details

The YMRS scale consists of 11 items, with 4 items weighted double (0-8 points) and 7 items with standard weighting (0-4 points). The total score ranges from 0 to 60.

### Double-weighted Items (0-8 points each):
1. Irritability
2. Speech (Rate & Amount)
3. Content
4. Aggressive Behavior

### Standard Items (0-4 points each):
1. Mood Elevation
2. Activity / Energy
3. Sexual Interest
4. Sleep
5. Thinking & Language Disorder
6. Appearance
7. Insight

## Scoring Interpretation

| YMRS Total Score | Interpretation |
|------------------|----------------|
| **0-6 points**   | Normal         |
| **7-20 points**  | Hypomania      |
| **21-35 points** | Moderate Mania |
| **>35 points**   | Severe Mania   |

## Usage

The YMRS module integrates with the MentalPlay Quizzer framework to provide automated assessment of manic symptoms. It follows the same pattern as other modules (PHQ-9, K-SADS, C-SSRS) and can be used with the existing Quizzer infrastructure.

## Testing

To test the YMRS module, use the following command:

```bash
python -m pytest Quizzer/tests/test_YMRS.py -v
```

For a complete flow test with three patients:

```bash
python -m pytest Quizzer/tests/test_YMRS.py::test_three_patients -v
```

## Configuration

The module's configuration is defined in `config.yaml` and includes settings for scoring, logging, and answer format.

## Dependencies

- Python 3.8+
- MentalPlay Quizzer core modules

## License

This module is part of the MentalPlay project and follows the same licensing terms as the main project.
