import { useEffect } from 'react';
import { useSettingsStore } from '@/stores/settingsStore';

export function SettingsPanel() {
  const { settings, loading, error, fetchSettings, updateSettings } = useSettingsStore();

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  if (loading) {
    return (
      <div className="p-4">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-200 rounded w-1/4"></div>
          <div className="h-32 bg-gray-200 rounded"></div>
          <div className="h-4 bg-gray-200 rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="text-sm text-red-700">{error}</div>
        </div>
      </div>
    );
  }

  if (!settings) return null;

  return (
    <div className="p-4 space-y-6">
      <div>
        <h3 className="text-lg font-medium text-gray-900">Personal Information</h3>
        <div className="mt-2">
          <textarea
            rows={4}
            value={settings.personal_info}
            onChange={(e) => updateSettings({ personal_info: e.target.value })}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
            placeholder="Add information about yourself..."
          />
        </div>
      </div>

      <div>
        <h3 className="text-lg font-medium text-gray-900">Memory Context</h3>
        <div className="mt-2">
          <textarea
            rows={4}
            value={settings.memory}
            onChange={(e) => updateSettings({ memory: e.target.value })}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
            placeholder="Add memory context..."
          />
        </div>
      </div>

      <div>
        <h3 className="text-lg font-medium text-gray-900">OpenAI API Key</h3>
        <div className="mt-2">
          <input
            type="password"
            value={settings.openai_api_key || ''}
            onChange={(e) => updateSettings({ openai_api_key: e.target.value })}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
            placeholder="Enter your OpenAI API key..."
          />
        </div>
      </div>

      <div>
        <h3 className="text-lg font-medium text-gray-900">Model</h3>
        <div className="mt-2">
          <select
            value={settings.model}
            onChange={(e) => updateSettings({ model: e.target.value })}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
          >
            <option value="gpt-4-0125-preview">GPT-4 Turbo</option>
            <option value="gpt-4">GPT-4</option>
            <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
          </select>
        </div>
      </div>

      <div>
        <h3 className="text-lg font-medium text-gray-900">Suggested Prompts</h3>
        <div className="mt-2 space-y-2">
          {settings.suggested_prompts.map((prompt, index) => (
            <div key={index} className="flex items-center space-x-2">
              <input
                type="text"
                value={prompt}
                onChange={(e) => {
                  const newPrompts = [...settings.suggested_prompts];
                  newPrompts[index] = e.target.value;
                  updateSettings({ suggested_prompts: newPrompts });
                }}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              />
              <button
                onClick={() => {
                  const newPrompts = settings.suggested_prompts.filter((_, i) => i !== index);
                  updateSettings({ suggested_prompts: newPrompts });
                }}
                className="text-red-600 hover:text-red-700"
              >
                Remove
              </button>
            </div>
          ))}
          <button
            onClick={() => {
              updateSettings({
                suggested_prompts: [...settings.suggested_prompts, '']
              });
            }}
            className="text-indigo-600 hover:text-indigo-700 text-sm font-medium"
          >
            Add Prompt
          </button>
        </div>
      </div>
    </div>
  );
} 