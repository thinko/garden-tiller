# Developer Notes for playbook enhancements, operational notes, and Jinja2 templating
# ===================================================================================
## 💡 Key Takeaways

### For Developers
- **Always protect dict2items calls** with type checking
- **Keep Jinja2 templates simple** - complexity leads to type issues
- **Use validation tools** to prevent regressions
- **Always initialize result dictionaries** as empty dictionaries `{}`
- **Protect all dict2items calls** with `if variable is mapping else default_value`
- **Keep Jinja2 templates simple** - avoid complex nested conditionals
- **Use the validation script** when adding new dict2items usage
- **Test with actual lab data** to ensure robustness

### For Operations
- **Run validation scripts** before deploying playbook changes
- **Monitor logs** for any new templating warnings
- **Test with actual lab data** to ensure robustness
