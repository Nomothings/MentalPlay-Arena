# PHQ-9 Like Scale Development Tutorial

This tutorial guides you through creating a new mental health scale module following the PHQ-9 structure. The module consists of four core files:

1. `config.yaml` - Module configuration
2. `inquiries.json` - Question bank with metadata
3. `rules.json` - Scoring and navigation rules
4. `scoring.py` - Scoring calculation and interpretation

## File Structure Overview

```
module-name/
├── config.yaml       # Module configuration
├── inquiries.json    # Questions and metadata
├── rules.json        # Scoring and navigation rules
└── scoring.py        # Scoring logic
```

## 1. config.yaml

### Purpose
Defines the module's basic behavior, including scoring method, logging, and answer format.

### Template
```yaml
# Module Configuration

# Scoring Configuration
scoring:
  method: "summation"  # Use "summation" for PHQ-9 like scales

# Logging Configuration
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  file: "./logs/module_name.log"
  console: true

# Answer Configuration
answers:
  format: "json"  # Options: json, csv, excel
```

### Key Points
- Use `summation` for scales that sum individual question scores
- Adjust logging settings based on your needs
- Choose the answer format that works best for your use case

## 2. inquiries.json

### Purpose
Stores all questions with their metadata, answer options, and navigation information.

### Structure
```json
[
  {
    "question_id": "unique_id",
    "question_text": "Question text",
    "domain": "Assessment domain",
    "category": "Question category",
    "category_id": number,
    "answer_space": ["Option 1", "Option 2", "Option 3", "Option 4"],
    "action": "next_question_id"  # Use "None" for last question
  }
]
```

### Key Points
- **question_id**: Unique identifier (e.g., "1_1" for first question of first section)
- **domain**: Broad assessment area (e.g., "Depression Assessment")
- **category**: Specific construct being measured (e.g., "Anhedonia")
- **category_id**: Numeric ID matching rules.json
- **answer_space**: 4 options consistent across all questions ("Not at all", "Several days", "More than half the days", "Nearly every day")
- **action**: Next question ID or "None" for the final question

### Example Question
```json
{
  "question_id": "1_1",
  "question_text": "Over the past two weeks, how often have you had little interest or pleasure in doing things?",
  "domain": "Depression Assessment",
  "category": "Anhedonia",
  "category_id": 1,
  "answer_space": [
    "Not at all",
    "Several days",
    "More than half the days",
    "Nearly every day"
  ],
  "action": "1_2"
}
```

## 3. rules.json

### Purpose
Defines scoring rules and navigation for each question-answer pair.

### Structure
```json
[
  {
    "category_id": number,
    "rule": "question_id == answer_letter",
    "action": "next_question_id",
    "score": "numeric_score"
  }
]
```

### Key Points
- **category_id**: Matches the category_id from inquiries.json
- **rule**: Format: `"question_id == A"` where A/B/C/D correspond to answer options 1-4
- **action**: Next question ID (consistent with inquiries.json)
- **score**: Numeric value (0-3) for that answer
- Create 4 rules per question (one for each answer option)
- Last question should have action: "judge"

### Example Rules for One Question
```json
[
  {
    "category_id": 1,
    "rule": "1_1 == A",
    "action": "1_2",
    "score": "0"
  },
  {
    "category_id": 1,
    "rule": "1_1 == B",
    "action": "1_2",
    "score": "1"
  },
  {
    "category_id": 1,
    "rule": "1_1 == C",
    "action": "1_2",
    "score": "2"
  },
  {
    "category_id": 1,
    "rule": "1_1 == D",
    "action": "1_2",
    "score": "3"
  }
]
```

## 4. scoring.py

### Purpose
Implements the scoring calculation and interpretation logic.

### Template
```python
"""
Module Scoring Logic
"""

from typing import Dict, List, Tuple
import json
import os


def calculate_score(answers: List[Dict]) -> Tuple[int, str]:
    """
    Calculate total score based on answers
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Tuple of (total_score, severity_level)
    """
    # Ensure answers is a valid list
    if not isinstance(answers, list):
        total_score = 0
        return total_score, get_interpretation(total_score)
    
    # Get scores from answers if available
    relevant_scores = []
    for answer in answers:
        if 'score' in answer and answer['score'] and answer['score'] != '-1':
            try:
                relevant_scores.append(int(answer['score']))
            except ValueError:
                continue
    
    # If no scores in answers, calculate from rules
    if not relevant_scores:
        try:
            rules_path = os.path.join(os.path.dirname(__file__), 'rules.json')
            with open(rules_path, 'r') as f:
                rules = json.load(f)
            
            # Create score map
            score_map = {}
            for rule in rules:
                question_id = rule['rule'].split(' == ')[0]
                answer = rule['rule'].split(' == ')[1].strip('"')
                score = int(rule['score'])
                score_map[f"{question_id}_{answer}"] = score
            
            # Calculate scores from answers
            for answer in answers:
                question_id = answer.get('question_id', '')
                answer_text = answer.get('answer', '')
                score_key = f"{question_id}_{answer_text}"
                if score_key in score_map:
                    relevant_scores.append(score_map[score_key])
                    
        except Exception as e:
            print(f"Error calculating score from rules: {e}")
    
    # Calculate total score
    total_score = sum(relevant_scores) if relevant_scores else 0
    
    # Ensure valid score range (adjust based on your scale)
    total_score = max(0, min(27, total_score))
    
    # Get interpretation
    severity_level = get_interpretation(total_score)
    
    return total_score, severity_level


def get_interpretation(score: int) -> str:
    """
    Map total score to severity level
    
    Args:
        score: Total scale score
        
    Returns:
        Severity level interpretation
    """
    # Adjust these ranges based on your scale's validation
    if score <= 4:
        return "Minimal"
    elif score <= 9:
        return "Mild"
    elif score <= 14:
        return "Moderate"
    elif score <= 19:
        return "Moderately Severe"
    else:
        return "Severe"
```

### Key Points
- **calculate_score**: Main function that processes answers and returns total score with interpretation
- **get_interpretation**: Maps total score to severity levels (adjust ranges based on your scale)
- Handles edge cases and ensures valid score range
- Reads rules from rules.json if scores aren't directly provided

## Development Workflow

1. **Define Your Scale**: Identify the construct, number of questions, and severity ranges
2. **Create inquiries.json**: Add all questions with metadata and answer options
3. **Create rules.json**: Define scoring and navigation for each question-answer pair
4. **Create scoring.py**: Implement scoring logic and interpretation
5. **Create config.yaml**: Set up module configuration
6. **Test**: Verify the module works correctly with sample answers

## Example Usage

```python
# Sample usage of the scoring module
from scoring import calculate_score

# Sample answers
answers = [
    {"question_id": "1_1", "answer": "A"},
    {"question_id": "1_2", "answer": "B"},
    # ... all questions
]

# Calculate score
total_score, severity = calculate_score(answers)
print(f"Total Score: {total_score}, Severity: {severity}")
```

## Key Principles for PHQ-9 Like Scales

1. **Consistent Answer Format**: Use the same 4-point Likert scale across all questions
2. **Linear Navigation**: No branching logic - questions are asked in sequence
3. **Simple Summation Scoring**: Total score is sum of individual question scores
4. **Clear Severity Levels**: Map total scores to meaningful severity categories
5. **Standardized Question Structure**: Consistent metadata for all questions

By following this tutorial, you can quickly create a new mental health scale module that integrates seamlessly with the MentalPlay framework.