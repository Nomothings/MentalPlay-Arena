"""
 BPRS Scoring Module - Implements Brief Psychiatric Rating Scale scoring logic
"""

from typing import Dict, List, Tuple
import json
import os


def calculate_bprs_score(answers: List[Dict]) -> Tuple[int, Dict[str, int], str]:
    """
    Calculate BPRS score based on answers
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Tuple of (total_score, dimensions, interpretation)
    """
    # Ensure answers is a valid list
    if not isinstance(answers, list):
        return 0, {}, ""
    
    # Calculate dimensions first
    dimensions = calculate_bprs_dimensions(answers)
    
    # Calculate total score as sum of dimension scores
    total_score = dimensions['anxiety_depression'] + dimensions['lack_of_vitality'] + dimensions['thought_disorder'] + dimensions['activation'] + dimensions['hostility_suspiciousness']
    
    # Ensure score is in valid range (18-126)
    total_score = max(18, min(126, total_score))
    
    # Get interpretation
    interpretation = get_bprs_interpretation(total_score)
    
    return total_score, dimensions, interpretation


def calculate_bprs_dimensions(answers: List[Dict]) -> Dict[str, int]:
    """
    Calculate BPRS dimension scores based on answers
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Dictionary of dimension scores with keys: 
        'anxiety_depression', 'lack_of_vitality', 'thought_disorder', 'activation', 'hostility_suspiciousness'
    """
    # Dimension questions mapping according to BPRS factor structure
    anxiety_depression_questions = {1, 2, 5, 9}  # Anxiety Depression
    lack_of_vitality_questions = {3, 13, 16, 18}  # Lack of Vitality
    thought_disorder_questions = {4, 8, 12, 15}  # Thought Disorder
    activation_questions = {6, 7, 17}  # Activation
    hostility_suspiciousness_questions = {10, 11, 14}  # Hostility Suspiciousness
    
    # Initialize scores
    anxiety_depression_score = 0
    lack_of_vitality_score = 0
    thought_disorder_score = 0
    activation_score = 0
    hostility_suspiciousness_score = 0
    
    # Get scores from answers
    for answer in answers:
        # check whether a stored score exists
        if 'score' in answer and answer['score'] and answer['score'] != '-1':
            try:
                score = int(answer['score'])
                
                # Extract category_id from question_id (format: "1_X" where X is category_id)
                category_id = int(answer['question_id'].split('_')[1])
                
                # Add to dimension scores
                if category_id in anxiety_depression_questions:
                    anxiety_depression_score += score
                if category_id in lack_of_vitality_questions:
                    lack_of_vitality_score += score
                if category_id in thought_disorder_questions:
                    thought_disorder_score += score
                if category_id in activation_questions:
                    activation_score += score
                if category_id in hostility_suspiciousness_questions:
                    hostility_suspiciousness_score += score
            except (ValueError, KeyError):
                continue
    
    # if no score was found, compute it from the rules file
    if anxiety_depression_score == 0 and lack_of_vitality_score == 0 and thought_disorder_score == 0 and activation_score == 0 and hostility_suspiciousness_score == 0:
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
            
            # Calculate dimension scores based on answers
            for answer in answers:
                question_id = answer.get('question_id', '')
                answer_text = answer.get('answer', '')
                
                # Look up the score in the score map
                score_key = f"{question_id}_{answer_text}"
                if score_key in score_map:
                    score = score_map[score_key]
                    
                    # Extract category_id from question_id
                    category_id = int(question_id.split('_')[1])
                    
                    # Add to dimension scores
                    if category_id in anxiety_depression_questions:
                        anxiety_depression_score += score
                    if category_id in lack_of_vitality_questions:
                        lack_of_vitality_score += score
                    if category_id in thought_disorder_questions:
                        thought_disorder_score += score
                    if category_id in activation_questions:
                        activation_score += score
                    if category_id in hostility_suspiciousness_questions:
                        hostility_suspiciousness_score += score
                        
        except Exception as e:
            print(f"Error calculating dimension scores from rules: {e}")
    
    # Create dimensions dictionary
    dimensions = {
        'anxiety_depression': anxiety_depression_score,  # Anxiety Depression
        'lack_of_vitality': lack_of_vitality_score,  # Lack of Vitality
        'thought_disorder': thought_disorder_score,  # Thought Disorder
        'activation': activation_score,  # Activation
        'hostility_suspiciousness': hostility_suspiciousness_score  # Hostility Suspiciousness
    }
    
    return dimensions


def get_bprs_interpretation(score: int) -> str:
    """
    Get BPRS interpretation based on total score
    
    Args:
        score: Total BPRS score
        
    Returns:
        Severity level interpretation
    """
    if score <= 36:
        return "Level 1: Minimal or no psychopathology"
    elif score <= 54:
        return "Level 2: Mild psychopathology"
    elif score <= 72:
        return "Level 3: Moderate psychopathology"
    elif score <= 90:
        return "Level 4: Severe psychopathology"
    elif score <= 108:
        return "Level 5: Very severe psychopathology"
    else:
        return "Level 6: Extreme psychopathology"
