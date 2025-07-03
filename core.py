# core.py

import os
import pandas as pd
import json
from openai import OpenAI  # <-- 1. Updated Import
from dotenv import load_dotenv
from typing import Dict, Any, List

# Load environment variables from the .env file
load_dotenv()

# 2. Initialize the OpenAI client with your API key
# This is the new, recommended way to set up the connection.
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_financial_data_with_ai(text: str, tables_data: str) -> Dict[str, Any]:
    """
    Sends the document text to the OpenAI API to extract raw financial figures.
    This function delegates the complex task of understanding document layouts to the AI.
    The prompt is the instruction manual for the AI, telling it exactly what to find and what JSON format to return.
    """
    PROMPT = """
You are an expert Tax Accountant AI specializing in Dutch Corporate Tax (VPB).
Your task is to analyze the provided financial documents and extract raw figures for each available quarter (Q1, Q2, Q3, Q4).

**Instructions:**
- Analyze the document to identify data for each quarter based on column headers or section titles (e.g., "Q1 2024", "3 Months Ending Mar 31").
- If the document is an annual summary without a quarterly breakdown, place all figures under the "Q4" key as a fallback.
- If a specific figure is not found for a quarter, use the numeric value 0.0.
- Return ONLY a valid JSON object.

**JSON Structure to return:**
{
  "company_name": "...",
  "country": "Netherlands",
  "accounting_period_year": "YYYY",
  "currency": "EUR",
  "quarters": {
    "Q1": { "total_revenue": 0.0, "total_operating_expenses": 0.0, "book_depreciation": 0.0, "tax_adjustments": { "non_deductible_expenses": 0.0, "tax_exempt_income": 0.0 } },
    "Q2": { "total_revenue": 0.0, "total_operating_expenses": 0.0, "book_depreciation": 0.0, "tax_adjustments": { "non_deductible_expenses": 0.0, "tax_exempt_income": 0.0 } },
    "Q3": { "total_revenue": 0.0, "total_operating_expenses": 0.0, "book_depreciation": 0.0, "tax_adjustments": { "non_deductible_expenses": 0.0, "tax_exempt_income": 0.0 } },
    "Q4": { "total_revenue": 0.0, "total_operating_expenses": 0.0, "book_depreciation": 0.0, "tax_adjustments": { "non_deductible_expenses": 0.0, "tax_exempt_income": 0.0 } }
  },
  "overall_figures_if_available": { "available_loss_carryforward_at_start_of_year": 0.0 }
}
"""
    combined_input = f"DOCUMENT TEXT:\n{text}\n\nTABLES DATA:\n{tables_data}"
    try:
        # 3. This is the new syntax for making the API call.
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": PROMPT.strip()},
                {"role": "user", "content": combined_input[:16000]}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        # Load the JSON string from the AI's response into a Python dictionary
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"Error during AI extraction: {e}")
        return {"error": f"AI extraction failed: {e}"}

def _compute_tax_for_period(figures: Dict[str, Any]) -> Dict[str, float]:
    """
    A reusable helper function to run the step-by-step tax computation for a single period (like one quarter).
    This function contains the core tax logic BEFORE annual adjustments like loss carryforward.
    """
    revenue = float(figures.get("total_revenue", 0))
    expenses = float(figures.get("total_operating_expenses", 0))
    depreciation = float(figures.get("book_depreciation", 0))
    # Step 1: Calculate Accounting Profit Before Tax (APBT)
    apbt = revenue - expenses - depreciation

    adjustments = figures.get("tax_adjustments", {})
    non_deductible = float(adjustments.get("non_deductible_expenses", 0))
    tax_exempt = float(adjustments.get("tax_exempt_income", 0))
    
    # Step 2: Calculate profit after standard tax adjustments
    taxable_profit_for_period = apbt + non_deductible - tax_exempt

    # Step 3: Apply Dutch tax rates to the period's profit
    if taxable_profit_for_period <= 200_000:
        tax_owed = taxable_profit_for_period * 0.19
    else:
        tax_owed = (200_000 * 0.19) + ((taxable_profit_for_period - 200_000) * 0.258)
    
    # Ensure tax is not negative if the company made a loss in the period
    final_tax_owed = max(0, tax_owed)

    # Return a structured dictionary with the full calculation breakdown
    return {
        "Total Revenue": revenue,
        "Total Expenses (incl. Depreciation)": expenses + depreciation,
        "Accounting Profit Before Tax": apbt,
        "Add: Non-Deductible Expenses": non_deductible,
        "Subtract: Tax-Exempt Income": tax_exempt,
        "Taxable Profit for Period": taxable_profit_for_period,
        "Tax Owed for Period": final_tax_owed,
    }

def process_financial_document(ai_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    This is the main orchestrator function. It takes the AI-extracted data and:
    1. Computes tax for each quarter individually using the helper function.
    2. Aggregates quarterly results to create a verifiable annual total.
    3. Applies annual-only adjustments like loss carryforward to the total.
    4. Compiles the final report object to be sent to the frontend.
    """
    try:
        quarterly_computations = {}
        for q_name, q_figures in ai_data.get("quarters", {}).items():
            if q_figures and q_figures.get('total_revenue', 0) > 0:
                computation = _compute_tax_for_period(q_figures)
                quarterly_computations[q_name] = computation

        if not quarterly_computations:
            return {"error": "No valid quarterly data with revenue was found to process."}

        df = pd.DataFrame(quarterly_computations.values())
        overall_summary = df.sum().to_dict()

        annual_profit_before_losses = overall_summary.get("Taxable Profit for Period", 0)
        available_losses = float(ai_data.get("overall_figures_if_available", {}).get("available_loss_carryforward_at_start_of_year", 0))
        
        losses_to_use = 0
        if annual_profit_before_losses > 0 and available_losses > 0:
            if annual_profit_before_losses <= 1_000_000:
                losses_to_use = min(annual_profit_before_losses, available_losses)
            else:
                offset_first_million = min(1_000_000, available_losses)
                remaining_profit = annual_profit_before_losses - 1_000_000
                remaining_losses = available_losses - offset_first_million
                offset_remainder = min(remaining_profit * 0.5, remaining_losses)
                losses_to_use = offset_first_million + offset_remainder
        
        final_annual_taxable_profit = annual_profit_before_losses - losses_to_use
        
        if final_annual_taxable_profit <= 200_000:
            final_annual_tax_owed = final_annual_taxable_profit * 0.19
        else:
            final_annual_tax_owed = (200_000 * 0.19) + ((final_annual_taxable_profit - 200_000) * 0.258)
        final_annual_tax_owed = max(0, final_annual_tax_owed)
        
        ordered_overall = {
            "Total Revenue": overall_summary.get("Total Revenue"),
            "Total Expenses (incl. Depreciation)": overall_summary.get("Total Expenses (incl. Depreciation)"),
            "Accounting Profit Before Tax": overall_summary.get("Accounting Profit Before Tax"),
            "Profit Before Loss Compensation": annual_profit_before_losses,
            "Subtract: Losses Utilized": -losses_to_use,
            "Final Taxable Profit for Year": final_annual_taxable_profit,
            "FINAL TAX OWED FOR YEAR": final_annual_tax_owed
        }

        return {
            "company_info": { "name": ai_data.get("company_name"), "year": ai_data.get("accounting_period_year")},
            "quarters": quarterly_computations,
            "overall": ordered_overall,
            "audit_flags": audit_risk_flags(ordered_overall),
            "raw_ai_extraction": ai_data
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"An error occurred during computation: {e}"}

def audit_risk_flags(overall_data: Dict[str, float]) -> List[str]:
    """Runs simple checks on the final annual figures to flag potential issues."""
    flags = []
    if overall_data.get("Accounting Profit Before Tax", 0) < 0:
        flags.append("Company reported an accounting loss for the year.")
    revenue = overall_data.get("Total Revenue", 1)
    expenses = overall_data.get("Total Expenses (incl. Depreciation)", 0)
    if expenses > revenue and revenue > 0:
        flags.append("⚠️ Total annual expenses exceed total annual revenue.")
    return flags