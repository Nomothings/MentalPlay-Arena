"""
C-SSRS Scoring Module - Implements C-SSRS scoring logic
"""

from typing import Dict, List, Tuple


def calculate_cssrs_score(answers: List[Dict]) -> int:
    """
    Calculate C-SSRS risk level based on answers
    
    Args:
        answers: List of answers, each with 'question_id' and 'answer' keys
        
    Returns:
        Risk level (integer)
    """
    # Ensure answers is a valid list
    if not isinstance(answers, list):
        return 1
    
    # Get scores from answers，and handle the Yes answer to question 2_2 specially
    relevant_scores = []
    has_question_2_2_yes = False
    
    for answer in answers:
        # check specifically whether question 2_2 was answered Yes
        if isinstance(answer, dict) and answer.get('question_id') == '2_2' and \
           (answer.get('answer') == 'A' or answer.get('answer', '').lower() == 'yes'):
            has_question_2_2_yes = True
            relevant_scores.append(6)  # directly add the maximum score 6
        
        # also check whether a stored score exists
        elif 'score' in answer and answer['score'] and answer['score'] != '-1':
            try:
                relevant_scores.append(int(answer['score']))
            except ValueError:
                continue
    
    # if there are relevant scores, return the highest (most severe risk level)
    if relevant_scores:
        risk_level = max(relevant_scores)
    else:
        # fallback: if no score was found, count the number of "Yes" answers
        yes_count = 0
        for answer in answers:
            if isinstance(answer, dict) and 'answer' in answer and \
               (answer['answer'].lower() == 'yes' or answer['answer'] == 'A' or answer['answer'].lower() == 'y'):
                yes_count += 1
        
        # return the appropriate risk level from yes_count
        if yes_count == 0:
            risk_level = 1  # no Yes answers; return the lowest risk level 1
        elif yes_count == 1:
            risk_level = 1
        elif yes_count == 2:
            risk_level = 2
        elif yes_count == 3:
            risk_level = 3
        elif yes_count == 4:
            risk_level = 4
        else:
            risk_level = 6  # five or more Yes answers; return the highest risk level
    
    # ensure the risk level stays within the valid range (1-6)
    risk_level = max(1, min(6, risk_level))
    
    return risk_level


def get_cssrs_interpretation(risk_level: int) -> str:
    """
    Get C-SSRS interpretation based on risk level
    
    Args:
        risk_level: C-SSRS risk level (1-6)
        
    Returns:
        Risk level description
    """
    risk_descriptions = {
        1: "Response 1: No Suicidal Ideation",
        2: "Response 2: Passive Suicidal Ideation",
        3: "Response 3: Active Suicidal Ideation (No Specific Method)",
        4: "Response 4: Suicidal Method Conception",
        5: "Response 5: Plan But No Action",
        6: "Response 6: Suicidal Behavior"
    }
    
    return risk_descriptions.get(risk_level, "Unknown Risk Level")