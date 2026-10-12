"""
K-SADS Scoring Module

This module implements the scoring logic for the K-SADS (Kiddie Schedule for Affective Disorders and Schizophrenia)
screening scale for affective disorders and schizophrenia in children and adolescents.
"""


def calculate_ksads_score(scores):
    """
    Calculate the K-SADS total score
    
    Args:
        scores: A list containing scores for each module
        
    Returns:
        dict: A dictionary containing the total score and module scores
    """
    total_score = 0
    
    for score in scores:
        try:
            total_score += int(score.get('score', 0))
        except (ValueError, TypeError):
            continue
    
    return {
        'total_score': total_score,
        'module_scores': scores
    }


def get_ksads_interpretation(score):
    """
    Get interpretation of the K-SADS score
    
    Args:
        score: Total score
        
    Returns:
        str: Score interpretation
    """
    if score < 10:
        return "Normal Range"
    elif score < 20:
        return "Mild Symptoms"
    elif score < 30:
        return "Moderate Symptoms"
    else:
        return "Severe Symptoms"


def get_threshold_analysis(scores):
    """
    Perform threshold analysis to determine which modules reach the threshold
    
    Args:
        scores: A list containing scores for each module
        
    Returns:
        dict: A dictionary containing threshold analysis results
    """
    subthreshold_categories = []
    clinical_categories = []
    
    for score in scores:
        category = {
            'category_id': score.get('category_id', 0),
            'domain': score.get('domain', 'Unknown'),
            'category': score.get('category_name', 'Unknown'),
            'score': score.get('score', 0)
        }
        
        try:
            score_value = int(score.get('score', 0))
            if score_value >= 2:
                # Score 2 or 3: Clinical
                clinical_categories.append(category)
            else:
                # Score 1: Subthreshold
                subthreshold_categories.append(category)
        except (ValueError, TypeError):
            # Scores that cannot be converted to integer are considered subthreshold
            subthreshold_categories.append(category)
    
    return {
        'subthreshold_count': len(subthreshold_categories),
        'clinical_count': len(clinical_categories),
        'subthreshold_categories': subthreshold_categories,
        'clinical_categories': clinical_categories,
        'clinical_percentage': round(len(clinical_categories) / len(scores) * 100, 1) if scores else 0
    }


def get_severity_assessment(scores):
    """
    Get severity assessment
    
    Args:
        scores: A list containing scores for each module
        
    Returns:
        dict: A dictionary containing lists of modules by severity level
    """
    normal_range = []
    mild_symptoms = []
    moderate_symptoms = []
    severe_symptoms = []
    
    for score in scores:
        category = {
            'category_id': score.get('category_id', 0),
            'domain': score.get('domain', 'Unknown'),
            'category': score.get('category_name', 'Unknown'),
            'score': score.get('score', 0)
        }
        
        try:
            score_value = int(score.get('score', 0))
            if score_value == 1:
                normal_range.append(category)
            elif score_value == 2:
                mild_symptoms.append(category)
            elif score_value == 3:
                moderate_symptoms.append(category)
            else:
                severe_symptoms.append(category)
        except (ValueError, TypeError):
            normal_range.append(category)
    
    return {
        'Normal Range': normal_range,
        'Mild Symptoms': mild_symptoms,
        'Moderate Symptoms': moderate_symptoms,
        'Severe Symptoms': severe_symptoms
    }


def get_domain_details(scores):
    """
    Get detailed information for each domain
    
    Args:
        scores: A list containing scores for each module
        
    Returns:
        dict: A dictionary containing detailed information for each domain
    """
    domain_details = {}
    
    for score in scores:
        domain = score.get('domain', 'Unknown')
        category_id = score.get('category_id', 0)
        category_name = score.get('category_name', 'Unknown')
        
        try:
            score_value = int(score.get('score', 0))
        except (ValueError, TypeError):
            score_value = 0
        
        status = "Clinical" if score_value >= 2 else "Subthreshold"
        
        if domain not in domain_details:
            domain_details[domain] = {
                'categories': [],
                'total_score': 0,
                'max_score': 0,
                'avg_score': 0,
                'clinical_count': 0,
                'total_count': 0
            }
        
        domain_details[domain]['categories'].append({
            'category_id': category_id,
            'name': category_name,
            'score': score_value,
            'status': status
        })
        
        domain_details[domain]['total_score'] += score_value
        domain_details[domain]['max_score'] = max(domain_details[domain]['max_score'], score_value)
        domain_details[domain]['total_count'] += 1
        
        if status == "Clinical":
            domain_details[domain]['clinical_count'] += 1
    
    # Calculate average score
    for domain in domain_details:
        if domain_details[domain]['total_count'] > 0:
            domain_details[domain]['avg_score'] = round(
                domain_details[domain]['total_score'] / domain_details[domain]['total_count'],
                2
            )
    
    return domain_details


def get_risk_level(clinical_percentage):
    """
    Determine risk level based on clinical module percentage
    
    Args:
        clinical_percentage: Clinical module percentage
        
    Returns:
        str: Risk level
    """
    if clinical_percentage < 20:
        return "Low Risk"
    elif clinical_percentage < 50:
        return "Moderate Risk"
    else:
        return "High Risk"


def generate_ksads_report(scores):
    """
    Generate a complete K-SADS report
    
    Args:
        scores: A list containing scores for each module
        
    Returns:
        dict: A complete K-SADS report
    """
    # Calculate total score
    total_score = 0
    for score in scores:
        try:
            total_score += int(score.get('score', 0))
        except (ValueError, TypeError):
            continue
    
    # Perform threshold analysis
    threshold_analysis = get_threshold_analysis(scores)
    
    # Perform severity assessment
    severity_assessment = get_severity_assessment(scores)
    
    # Get domain details
    domain_details = get_domain_details(scores)
    
    # Determine risk level
    risk_level = get_risk_level(threshold_analysis['clinical_percentage'])
    
    # Generate summary
    summary = {
        'overall_status': {
            'total_categories_assessed': len(scores),
            'subthreshold_categories': threshold_analysis['subthreshold_count'],
            'clinical_categories': threshold_analysis['clinical_count'],
            'clinical_percentage': threshold_analysis['clinical_percentage'],
            'risk_level': risk_level
        },
        'key_findings': [],
        'conclusion': "",
        'recommendation': ""
    }
    
    # Generate key findings
    if threshold_analysis['clinical_count'] > 0:
        # Get top 5 scoring modules
        top_scores = sorted(
            scores,
            key=lambda x: int(x.get('score', 0)) if isinstance(x.get('score'), (int, str)) else 0,
            reverse=True
        )[:5]
        
        for score in top_scores:
            summary['key_findings'].append(
                f"• {score.get('domain', 'Unknown')} - {score.get('category_name', 'Unknown')}: Score {score.get('score', 0)}"
            )
    
    # Generate conclusion
    if threshold_analysis['clinical_count'] == 0:
        summary['conclusion'] = "No obvious psychiatric symptoms were found."
        summary['recommendation'] = "It is recommended to continue maintaining a healthy lifestyle and undergo regular mental health check-ups."
    elif threshold_analysis['clinical_percentage'] < 50:
        summary['conclusion'] = "Mild psychiatric symptoms were found, requiring further observation."
        summary['recommendation'] = "It is recommended to pay attention to mental health status and seek professional psychological assessment when necessary."
    else:
        summary['conclusion'] = "Obvious psychiatric symptoms were found, requiring professional intervention."
        summary['recommendation'] = "It is recommended to seek professional mental health assessment and treatment as soon as possible."
    
    return {
        'total_score': total_score,
        'threshold_analysis': threshold_analysis,
        'severity_assessment': severity_assessment,
        'domain_details': domain_details,
        'risk_alerts': {
            'high_risk_domains': [],
            'critical_categories': [],
            'has_critical_risk': False,
            'risk_level': risk_level
        },
        'summary': summary
    }