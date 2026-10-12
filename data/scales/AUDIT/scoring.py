"""
AUDIT Scoring Module - Implements AUDIT scoring logic
"""

from typing import Dict, List, Tuple
import json
import os


def calculate_audit_score(answers: List[Dict]) -> int:
    """
    Calculate AUDIT score based on answers
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Total AUDIT score
    """
    # Ensure answers is a valid list
    if not isinstance(answers, list):
        return 0
    
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
    
    # Ensure score is in valid range (0-40)
    total_score = max(0, min(40, total_score))
    
    return total_score


def get_audit_interpretation(score: int) -> str:
    """
    Get AUDIT interpretation based on total score
    
    Args:
        score: Total AUDIT score
        
    Returns:
        Severity level interpretation
    """
    if score <= 4:
        return "Low Risk"
    elif score <= 14:
        return "Medium Risk"
    elif score <= 19:
        return "High Risk"
    else:
        return "Very High Risk"


def calculate_score(answers: List[Dict]) -> Tuple[int, str]:
    """
    Calculate AUDIT score and get interpretation
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Tuple of (total_score, severity_level)
    """
    total_score = calculate_audit_score(answers)
    severity_level = get_audit_interpretation(total_score)
    return total_score, severity_level
