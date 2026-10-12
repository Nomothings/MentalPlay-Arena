"""
SCAS-S Scoring Module - Implements SCAS-S scoring logic
"""

from typing import Dict, List, Tuple
import json
import os


def calculate_scass_score(answers: List[Dict]) -> int:
    """
    Calculate SCAS-S score based on answers
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Total SCAS-S score
    """
    # Ensure answers is a valid list
    if not isinstance(answers, list):
        return 0
    
    # Get the score set in the rules from answers
    relevant_scores = []
    for answer in answers:
        # check whether a stored score exists
        if 'score' in answer and answer['score'] and answer['score'] != '-1':
            try:
                relevant_scores.append(int(answer['score']))
            except ValueError:
                continue
    
    # if no score was found, compute it from the rules file
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
    
    # Ensure score is in valid range (0-57)
    total_score = max(0, min(57, total_score))
    
    return total_score


def get_scass_interpretation(score: int) -> str:
    """
    Get SCAS-S interpretation based on total score
    
    Args:
        score: Total SCAS-S score
        
    Returns:
        Severity level interpretation
    """
    if score <= 18:
        return "Mild"
    elif score <= 35:
        return "Moderate"
    else:
        return "Severe"


def calculate_score(answers: List[Dict]) -> Tuple[int, str]:
    """
    Calculate SCAS-S score and interpretation based on answers
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Tuple of (total_score, severity_level)
    """
    total_score = calculate_scass_score(answers)
    interpretation = get_scass_interpretation(total_score)
    return total_score, interpretation
