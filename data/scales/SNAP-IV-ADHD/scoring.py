"""
Module Scoring Logic for SNAP-IV ADHD Assessment

Usage:
    from scoring import calculate_score
    
    answers = [
        {"question_id": "1_1", "answer": "A"},
        {"question_id": "1_2", "answer": "B"},
        # ... all 18 questions
    ]
    
    total_score, severity = calculate_score(answers)
    print(f"Total Score: {total_score}, Severity: {severity}")
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
    
    # Ensure valid score range (0-54 for SNAP-IV ADHD)
    total_score = max(0, min(54, total_score))
    
    # Get interpretation
    severity_level = get_interpretation(total_score)
    
    return total_score, severity_level


def get_interpretation(score: int) -> str:
    """
    Map total score to severity level
    
    Args:
        score: Total scale score (0-54)
        
    Returns:
        Severity level interpretation
    """
    if score <= 18:
        return "Good"
    elif score <= 26:
        return "Normal"
    elif score <= 36:
        return "Moderate"
    else:
        return "Severe"