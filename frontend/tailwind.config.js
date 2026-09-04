import colors from 'tailwindcss/colors'
import frappeUIPreset from 'frappe-ui/tailwind'

export default {
  presets: [frappeUIPreset],
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
    './node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // the frappe-ui preset REPLACES tailwind's palette and ships no
        // indigo family; restore it for our accent color
        indigo: colors.indigo,
      },
    },
  },
}
