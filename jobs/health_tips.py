# jobs/health_tips.py - Health tips content by condition
import random
from datetime import datetime

HEALTH_TIPS = {
    "Diabetes": [
        "🍽️ **Portion Control Tip**: Use the plate method - fill half your plate with non-starchy vegetables, a quarter with lean protein, and a quarter with whole grains.",
        "🚶 **Post-Meal Walk**: A 10-15 minute walk after meals can help lower your blood sugar by 20-30 points. Start today!",
        "👣 **Foot Care**: Check your feet daily for cuts, blisters, or changes. Diabetes can reduce sensation, making injuries easy to miss.",
        "💧 **Stay Hydrated**: Drink 8-10 glasses of water daily. Proper hydration helps your kidneys flush out excess blood sugar.",
        "😴 **Sleep Matters**: Aim for 7-8 hours of quality sleep. Poor sleep can raise blood sugar and make diabetes harder to control.",
        "🥗 **Carb Counting**: Learn to count carbs - most adults with diabetes aim for 45-60 grams per meal. Apps can help track this!",
        "📊 **Pattern Tracking**: Keep a log of blood sugar readings, meals, and activity. Patterns help you and your doctor adjust treatment.",
        "🍬 **Hypoglycemia Kit**: Always carry glucose tablets or hard candy. Treat low blood sugar immediately with 15g of fast-acting carbs.",
        "👀 **Eye Exams**: Get a dilated eye exam yearly. Diabetic retinopathy can be prevented if caught early.",
        "💪 **Strength Training**: Add resistance exercises twice weekly. Building muscle helps your body use insulin more effectively.",
        "🌾 **Fiber Power**: Aim for 25-30g of fiber daily. Fiber slows sugar absorption and helps control blood glucose levels.",
        "⏰ **Medication Timing**: Take medications at the same time daily. Set phone reminders to never miss a dose.",
    ],
    
    "Hypertension": [
        "🧂 **DASH Diet**: Follow the DASH eating plan - rich in fruits, vegetables, whole grains, and low-fat dairy. It can lower BP by 11 points!",
        "🧂 **Salt Awareness**: Limit sodium to 2,300mg daily (1 teaspoon). Read labels - processed foods hide surprising amounts of salt.",
        "🧘 **Stress Management**: Practice deep breathing for 5 minutes daily. Chronic stress keeps your blood pressure elevated.",
        "📱 **Home Monitoring**: Check BP at the same time daily. Morning readings give the most accurate picture of your control.",
        "☕ **Caffeine Check**: Caffeine can spike BP by 10 points. If you're sensitive, switch to decaf or herbal tea.",
        "🍌 **Potassium Power**: Eat potassium-rich foods like bananas, sweet potatoes, and spinach. They help balance sodium's effects.",
        "🚭 **Quit Smoking**: Each cigarette raises BP for 20+ minutes. Quitting is the single best thing you can do for your heart.",
        "🏃 **Cardio Exercise**: Aim for 150 minutes of moderate exercise weekly. Even 30 minutes of brisk walking 5 days a week works!",
        "🍷 **Alcohol Limits**: Men: max 2 drinks/day. Women: max 1 drink/day. Excess alcohol raises blood pressure significantly.",
        "😴 **Sleep Position**: Sleep on your left side to improve blood flow and reduce pressure on blood vessels.",
        "⚖️ **Weight Loss**: Losing just 5-10 pounds can lower BP by 5-10 points if you're overweight.",
        "💊 **Medication Consistency**: Take BP meds at the same time daily, even if you feel fine. High BP has no symptoms!",
    ],
    
    "High Cholesterol": [
        "🥑 **Healthy Fats**: Replace butter with olive oil or avocado. These monounsaturated fats can lower LDL cholesterol.",
        "🐟 **Omega-3 Rich**: Eat fatty fish (salmon, mackerel) twice weekly. Omega-3s reduce triglycerides and boost HDL (good cholesterol).",
        "🌾 **Soluble Fiber**: Oats, beans, and apples contain soluble fiber that blocks cholesterol absorption. Aim for 10-25g daily.",
        "🥜 **Nuts Daily**: A handful of almonds or walnuts daily can lower LDL by 5%. They're heart-healthy snacks!",
        "🚫 **Trans Fat Ban**: Avoid foods with 'partially hydrogenated oils'. Trans fats raise bad cholesterol and lower good cholesterol.",
        "🏃 **Move More**: 30 minutes of exercise 5x/week raises HDL (good cholesterol) and lowers LDL (bad cholesterol).",
        "🍎 **Plant Sterols**: Foods fortified with plant sterols (some margarines, orange juice) can lower LDL by 10%.",
        "⚖️ **Lose Excess Weight**: Every 10 pounds lost can reduce cholesterol by 5-8 points. Even small losses help!",
        "🍷 **Moderate Red Wine**: One glass daily may boost HDL. But don't start drinking if you don't already - other methods work too!",
        "🥚 **Egg Myths**: You can eat eggs! Dietary cholesterol has less impact than saturated fat. Limit to 7 eggs/week to be safe.",
        "📖 **Read Labels**: Look for foods with less than 2g saturated fat per serving. Saturated fat raises LDL more than anything.",
        "💊 **Statin Timing**: Take statins at night - your body makes most cholesterol while you sleep, so nighttime dosing is most effective.",
    ],
    
    "Heart Disease": [
        "⚠️ **Know Warning Signs**: Chest pain, shortness of breath, arm/jaw pain, sudden sweating - call emergency services immediately!",
        "💊 **Aspirin Therapy**: If prescribed, take low-dose aspirin daily. It prevents blood clots but only if recommended by your doctor.",
        "🌡️ **Temperature Care**: Extreme cold or heat strains your heart. Dress appropriately and avoid strenuous outdoor activity in extremes.",
        "✈️ **Travel Smart**: Long flights increase clot risk. Walk every 2 hours, stay hydrated, and wear compression socks if advised.",
        "😴 **Sleep Apnea**: Loud snoring and daytime fatigue? Ask about sleep apnea - it significantly increases heart disease risk.",
        "🥗 **Mediterranean Diet**: This diet reduces heart attacks by 30%. Focus on olive oil, fish, nuts, fruits, and vegetables.",
        "💪 **Cardiac Rehab**: If recommended, complete cardiac rehabilitation. It reduces death risk by 25% and improves quality of life.",
        "😰 **Stress & Depression**: Both double your heart attack risk. Seek help - therapy and medication are effective treatments.",
        "🦷 **Dental Care**: Brush and floss daily. Gum disease bacteria can enter bloodstream and cause heart inflammation.",
        "💉 **Flu Shot**: Get annual flu vaccine. Flu doubles heart attack risk in the weeks following infection.",
        "👫 **Social Connection**: Loneliness increases heart disease risk by 30%. Stay connected with friends and family.",
        "📊 **Know Your Numbers**: Check blood pressure, cholesterol, and blood sugar regularly. Managing these protects your heart.",
    ],
    
    "Kidney Disease": [
        "💧 **Fluid Balance**: Drink as much as your doctor recommends - too much or too little both harm kidneys. Track your intake!",
        "🍖 **Protein Control**: Limit protein to recommended amount. Excess protein makes kidneys work harder. Choose quality over quantity.",
        "🧂 **Low Sodium**: Keep sodium under 2,000mg daily. It prevents fluid retention and reduces blood pressure strain on kidneys.",
        "🍌 **Potassium Watch**: Damaged kidneys can't remove potassium well. Avoid high-potassium foods if levels are elevated.",
        "💊 **Medication Safety**: Avoid ibuprofen, naproxen, and herbal supplements. Many harm kidneys. Always check with your doctor first!",
        "📊 **Monitor Output**: Track urine output and color. Dark urine or swelling means you need to contact your doctor.",
        "🍺 **Limit Alcohol**: Alcohol taxes kidneys and can worsen damage. Stick to your doctor's recommendations or avoid completely.",
        "🍪 **Phosphorus Limit**: Avoid processed foods, colas, and dairy in excess. High phosphorus weakens bones in kidney disease.",
        "⚖️ **Weight Control**: Obesity worsens kidney disease. Even 5-10% weight loss significantly helps kidney function.",
        "📈 **Blood Sugar Control**: Keep A1C under 7% if diabetic. High blood sugar is the #1 cause of kidney failure.",
        "🩸 **Blood Pressure**: Keep BP under 130/80. This is THE most important thing you can do to slow kidney disease progression.",
        "🚭 **Stop Smoking**: Smoking accelerates kidney disease progression and doubles your risk of kidney failure. Quit today!",
    ],
    
    "Thyroid Disorder": [
        "💊 **Timing Matters**: Take thyroid medication on an empty stomach, 30-60 minutes before breakfast. Consistency is key!",
        "☕ **Avoid Interactions**: Wait 4 hours after thyroid med before taking iron, calcium, or antacids. They block absorption.",
        "🥬 **Cruciferous Caution**: Eat broccoli, cabbage, and kale in moderation if hypothyroid. Raw forms can interfere with hormone production.",
        "🧂 **Iodine Balance**: Use iodized salt but don't overdo it. Too much iodine can worsen both hyper and hypothyroidism.",
        "😴 **Energy Management**: Hyperthyroid? Rest frequently and avoid overexertion. Hypothyroid? Light exercise can boost energy.",
        "📊 **Track Symptoms**: Keep a journal of energy, mood, weight, and heart rate. Patterns help your doctor adjust medication.",
        "🌡️ **Temperature Sensitivity**: Hypothyroid makes you cold-sensitive. Layer clothes and keep warm. Hyperthyroid? Stay cool.",
        "🍽️ **Selenium Foods**: Brazil nuts, tuna, and eggs contain selenium which supports thyroid function. Just 1-2 Brazil nuts daily!",
        "📱 **Medication Refills**: Never run out of thyroid medication. Set reminders to refill prescription when you have 1 week left.",
        "🔬 **Regular Testing**: Get TSH checked every 6-12 months. Thyroid needs change over time and medication requires adjustment.",
        "⚖️ **Weight Management**: Thyroid affects metabolism. Work with dietitian if weight changes concern you - it's not just willpower!",
        "😌 **Stress Reduction**: Stress can worsen thyroid symptoms. Practice relaxation techniques and prioritize self-care.",
    ]
}

def get_health_tip(conditions):
    """Get a random health tip based on patient's conditions"""
    if not conditions:
        return None
    
    # Pick a random condition from patient's conditions
    condition = random.choice(conditions)
    
    # Get tips for that condition
    if condition in HEALTH_TIPS:
        tips = HEALTH_TIPS[condition]
        return random.choice(tips)
    
    return None

async def send_health_tip_to_patient(patient_id, condition, db, whatsapp):
    """Send a specific health tip to a patient"""
    patient = await db.get_patient_by_id(patient_id)
    
    if not patient:
        return False
    
    tip = None
    if condition in HEALTH_TIPS:
        tip = random.choice(HEALTH_TIPS[condition])
    else:
        tip = get_health_tip(patient.get("health_conditions", []))
    
    if not tip:
        return False
    
    message = f"""💡 *Health Tip for {condition}*

Hi {patient['patient_name']}!

{tip}

Stay healthy! 🌟

Type *CARE* for menu."""
    
    await whatsapp.send_message(patient["whatsapp_number"], message)
    
    # Update last tip sent
    await db.update_patient(patient_id, {
        "last_health_tip_sent": datetime.utcnow()
    })
    
    return True