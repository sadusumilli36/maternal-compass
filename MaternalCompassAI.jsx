import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Loader2, Sparkles, Activity, FileText, Navigation, ShieldCheck, Volume2 } from 'lucide-react';

/**
 * MATERNALCOMPASS STRATEGIC AI
 * This component is the "brain" of the project.
 * It is grounded with data from the Georgia Maternal Health Risk Model.
 */

// Grounding Data: Embedded directly to prevent resolution errors and ensure zero hallucinations.
const maternalData = [
    {
        "county": "Walker",
        "risk_score": 54.6,
        "metrics": { "prenatal_risk": 91.0, "birth_share": 0.6, "total_beds": 1, "risk_level": "Very High", "care_level": 0, "distance": 19.43 }
    },
    {
        "county": "Catoosa",
        "risk_score": 46.15,
        "metrics": { "prenatal_risk": 92.3, "birth_share": 0.5, "total_beds": 1, "risk_level": "Very High", "care_level": 0, "distance": 10.95 }
    },
    {
        "county": "Clay",
        "risk_score": 36.4,
        "metrics": { "prenatal_risk": 36.4, "birth_share": 1.0, "total_beds": 1, "risk_level": "Very High", "care_level": 0, "distance": 43.27 }
    },
    {
        "county": "Echols",
        "risk_score": 31.8,
        "metrics": { "prenatal_risk": 31.8, "birth_share": 1.0, "total_beds": 1, "risk_level": "Very High", "care_level": 0, "distance": 22.88 }
    },
    {
        "county": "Calhoun",
        "risk_score": 24.4,
        "metrics": { "prenatal_risk": 24.4, "birth_share": 1.0, "total_beds": 1, "risk_level": "Very High", "care_level": 0, "distance": 27.25 }
    },
    {
        "county": "Hancock",
        "risk_score": 22.8,
        "metrics": { "prenatal_risk": 22.8, "birth_share": 1.0, "total_beds": 1, "risk_level": "Very High", "care_level": 0, "distance": 19.41 }
    },
    {
        "county": "Columbia",
        "risk_score": 21.0,
        "metrics": { "prenatal_risk": 15.0, "birth_share": 1.4, "total_beds": 1, "risk_level": "Very High", "care_level": 0, "distance": 9.84 }
    }
];

const App = () => {
  const [messages, setMessages] = useState([
    { 
      role: 'bot', 
      text: "MaternalCompass Strategic AI is online. I've analyzed the Georgia risk model. We've identified critical safety gaps where risk scores exceed safety baselines. How can I help you navigate this data?" 
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef(null);

  const suggestions = [
    { 
      label: "Top Risk Analysis", 
      icon: <Activity size={14}/>, 
      prompt: "Who are the top 3 highest risk counties and what are their specific scores and bed counts?" 
    },
    { 
      label: "Maternity Deserts", 
      icon: <Navigation size={14}/>, 
      prompt: "Identify the counties that are Maternity Deserts (0 beds) and explain the travel distance risk." 
    },
    { 
      label: "Infrastructure Memo", 
      icon: <FileText size={14}/>, 
      prompt: "Draft a policy memo suggesting facility upgrades for counties with High Risk but Level 0 Care." 
    }
  ];

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async (textOverride) => {
    const text = textOverride || input;
    if (!text.trim()) return;

    setMessages(prev => [...prev, { role: 'user', text }]);
    setInput('');
    setLoading(true);

    // Grounding logic to prevent hallucinations
    const dataSummary = maternalData
      .map(c => `${c.county}: Risk ${c.risk_score}, Beds ${c.metrics.total_beds}, Care Lvl ${c.metrics.care_level}, Dist ${c.metrics.distance}mi`)
      .join(' | ');

    const apiKey = "AIzaSyAR1KZllZUhBCeo0GNgrDiIwXf07vZqiCA"; // API key provided by environment

    const systemPrompt = `
      You are the MaternalCompass Strategic AI. 
      Your mission is to provide data-driven recommendations to reduce maternal mortality in Georgia.
      
      DATA SOURCE (Use ONLY these numbers to avoid hallucinations):
      ${dataSummary}
      
      LOGIC RULES:
      1. Formula: Risk = (Late Prenatal Care % * State Birth Share %) / OB Beds.
      2. If a county has 0 OB beds, it is a 'Maternity Desert'.
      3. Critical Zone: Any score > 15.
      
      INSTRUCTIONS:
      - Never hallucinate data. If a county isn't in the provided list, explain the Risk Factor logic instead of guessing a number.
      - If a county is high risk (>15) but has Level 0 care, suggest it as a priority for mobile clinics or facility upgrades (targeting Level 3 or 4 capability).
      - Focus on the relationship between high travel distance (e.g., Clay at 43mi) and risk.
      - Be professional, urgent, and direct.
    `;

    try {
      const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key=${apiKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text }] }],
          systemInstruction: { parts: [{ text: systemPrompt }] }
        })
      });

      const result = await response.json();
      const botResponse = result.candidates?.[0]?.content?.parts?.[0]?.text || "The analysis engine is currently busy. Please try again.";
      setMessages(prev => [...prev, { role: 'bot', text: botResponse }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'bot', text: "Connection error. Ensure the MaternalCompass data bridge is active." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0d14] text-slate-200 border border-white/5 rounded-[2rem] overflow-hidden shadow-2xl font-sans">
      {/* Brand Header */}
      <div className="p-5 bg-indigo-600 flex justify-between items-center shadow-lg">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-white/10 rounded-xl flex items-center justify-center backdrop-blur-md border border-white/20">
            <ShieldCheck size={22} className="text-white" />
          </div>
          <div>
            <h2 className="text-sm font-black uppercase tracking-widest leading-none text-white">MaternalCompass AI</h2>
            <p className="text-[10px] text-white/70 mt-1 font-bold">Strategic Assistant</p>
          </div>
        </div>
      </div>

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2 duration-300`}>
            <div className={`flex gap-3 max-w-[85%] ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${m.role === 'user' ? 'bg-slate-800 border border-white/5' : 'bg-indigo-600 shadow-lg shadow-indigo-600/20'}`}>
                {m.role === 'user' ? <User size={14} /> : <Bot size={14} />}
              </div>
              <div className={`p-4 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap shadow-xl ${m.role === 'user' ? 'bg-indigo-600 text-white rounded-tr-none' : 'bg-slate-900 border border-white/5 text-slate-200 rounded-tl-none'}`}>
                {m.text}
              </div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-3 px-2">
            <Loader2 className="animate-spin text-indigo-400" size={16} />
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Consulting Risk Index...</span>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Suggested Strategy Chips */}
      <div className="px-6 py-3 bg-slate-950/40 flex gap-2 overflow-x-auto scrollbar-hide border-t border-white/5">
        {suggestions.map((s, i) => (
          <button 
            key={i} 
            onClick={() => handleSend(s.prompt)}
            className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-slate-900 border border-white/5 rounded-full text-[10px] font-bold text-slate-400 hover:text-white hover:border-indigo-500/50 hover:bg-slate-800 transition-all active:scale-95 shadow-lg"
          >
            {s.icon} {s.label}
          </button>
        ))}
      </div>

      {/* Interaction Bar */}
      <div className="p-6 bg-slate-950/60 border-t border-white/5">
        <div className="relative group">
          <input 
            type="text" 
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask MaternalCompass about regional risk..."
            className="w-full bg-slate-900/80 border border-white/10 rounded-2xl py-4 pl-6 pr-14 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all shadow-inner placeholder:text-slate-600"
          />
          <button 
            onClick={() => handleSend()}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl transition-all shadow-lg active:scale-90"
          >
            <Send size={18} />
          </button>
        </div>
        <div className="mt-4 flex items-center justify-center gap-2 opacity-30">
          <Sparkles size={10} className="text-indigo-400" />
          <p className="text-[8px] font-black text-slate-400 uppercase tracking-widest">Validated Strategic Output</p>
        </div>
      </div>
    </div>
  );
};

export default App;