"""
GAD-7 Scoring Module - Implements GAD-7 scoring logic
"""

from typing import Dict, List, Tuple
import json
import os


def calculate_gad7_score(answers: List[Dict]) -> int:
    """
    Calculate GAD-7 score based on answers
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Total GAD-7 score
    """
    # Ensure answers is a valid list
    if not isinstance(answers, list):
        return 0
    
    # Get scores from answers if available
    relevant_scores = []
    for answer in answers:
        # Check if score is stored in answer
        if 'score' in answer and answer['score'] and answer['score'] != '-1':
            try:
                relevant_scores.append(int(answer['score']))
            except ValueError:
                continue
    
    # If no scores found in answers, calculate from rules
    if not relevant_scores:
        try:
            # Get the rules file path
            rules_path = os.path.join(os.path.dirname(__file__), 'rules.json')
            
            # Load rules
            with open(rules_path, 'r') as f:
                rules = json.load(f)
            
            # Create a dictionary to map question_id and answer to score
            score_map = {}
            for rule in rules:
                question_id = rule['rule'].split(' == ')[0]
                answer = rule['rule'].split(' == ')[1].strip('"')
                score = int(rule['score'])
                score_map[f"{question_id}_{answer}"] = score
            
            # Calculate total score based on answers
            for answer in answers:
                question_id = answer.get('question_id', '')
                answer_text = answer.get('answer', '')
                
                # Look up the score in the score map
                score_key = f"{question_id}_{answer_text}"
                if score_key in score_map:
                    relevant_scores.append(score_map[score_key])
                    
        except Exception as e:
            print(f"Error calculating score from rules: {e}")
    
    # Calculate total score
    total_score = sum(relevant_scores) if relevant_scores else 0
    
    # Ensure score is in valid range (0-21)
    total_score = max(0, min(21, total_score))
    
    return total_score


def get_gad7_interpretation(score: int) -> str:
    """
    Get GAD-7 interpretation based on total score
    
    Args:
        score: Total GAD-7 score
        
    Returns:
        Severity level interpretation
    """
    if score <= 4:
        return "None or minimal"
    elif score <= 9:
        return "Mild"
    elif score <= 14:
        return "Moderate"
    else:
        return "Severe"


def calculate_score(answers: List[Dict]) -> Tuple[int, str]:
    """
    Calculate GAD-7 score and get interpretation
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Tuple of (total_score, severity_level)
    """
    total_score = calculate_gad7_score(answers)
    severity_level = get_gad7_interpretation(total_score)
    return total_score, severity_level
