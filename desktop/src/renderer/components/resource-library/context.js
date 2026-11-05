import { inject } from 'vue'
export const resourceLibraryKey = Symbol('resource-library-panel')
export function useLibraryContext() {
 const model = inject(resourceLibraryKey, null)
 if (!model) throw new Error('Resource library section needs its panel controller')
 return model
}
