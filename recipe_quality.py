"""Drawing eligibility is structural, not a claim that all recipe facts are correct."""
def drawing_allowed(recipe):
    if recipe.get('analysis_status') != 'deepseek':
        return False, 'DeepSeek 未成功整理，不能使用本地规则草稿绘图。'
    model = recipe.get('deepseek') or {}
    if not model.get('ingredients') or not model.get('steps'):
        return False, '材料或步骤为空。'
    if model.get('uncertainties') and recipe.get('note_status') != 'needs_confirmation':
        return False, '原文存在不确定内容，需人工核对。'
    return True, ''
