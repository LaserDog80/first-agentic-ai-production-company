// Pixel-art character sprites used by the presentation view.
// Loaded as a plain script before the page's main <script>, exposing
// `CHARACTERS` as a global. Each entry: { id, name, role, pixels: [{ color, coords: [[x,y], …] }] }.
const CHARACTERS = [
    {
        id: 'series_producer',
        name: 'SERIES PRODUCER',
        role: 'Editorial Vision',
        // Pixel art: professional woman with glasses and blazer
        pixels: [
            // Hair (dark brown, longer — frames face)
            { color: '#2c1810', coords: [[2,-1],[3,-1],[4,-1],[5,-1],[1,0],[2,0],[3,0],[4,0],[5,0],[6,0],[1,1],[2,1],[3,1],[4,1],[5,1],[6,1],[0,2],[1,2],[6,2],[7,2],[0,3],[7,3],[0,4],[7,4],[0,5],[7,5]] },
            // Face (skin)
            { color: '#f4c089', coords: [[2,2],[3,2],[4,2],[5,2],[2,3],[3,3],[4,3],[5,3],[2,4],[3,4],[4,4],[5,4]] },
            // Glasses
            { color: '#6a5acd', coords: [[1,3],[6,3]] },
            // Eyes
            { color: '#1a1a1a', coords: [[3,3],[5,3]] },
            // Lips
            { color: '#d4636a', coords: [[3,4],[4,4]] },
            // Blazer (dark navy)
            { color: '#1a237e', coords: [[1,5],[2,5],[5,5],[6,5],[1,6],[2,6],[5,6],[6,6],[1,7],[2,7],[5,7],[6,7],[1,8],[2,8],[5,8],[6,8]] },
            // Blouse (cream)
            { color: '#f5f0e8', coords: [[3,5],[4,5],[3,6],[4,6],[3,7],[4,7]] },
            // Necklace accent
            { color: '#f5c542', coords: [[3,5],[4,5]] },
            // Hands (skin)
            { color: '#f4c089', coords: [[0,8],[7,8]] },
            // Skirt (dark)
            { color: '#0d1b4a', coords: [[2,9],[3,9],[4,9],[5,9],[2,10],[3,10],[4,10],[5,10]] },
            // Shoes (heels)
            { color: '#1a237e', coords: [[1,11],[2,11],[3,11],[4,11],[5,11],[6,11]] },
        ]
    },
    {
        id: 'producer',
        name: 'PRODUCER',
        role: 'Creative Coordinator',
        pixels: [
            // Headset
            { color: '#555', coords: [[1,0],[6,0],[0,1],[7,1],[0,2],[7,2]] },
            // Headset mic
            { color: '#e94560', coords: [[0,3],[0,4]] },
            // Hair
            { color: '#8b4513', coords: [[2,0],[3,0],[4,0],[5,0],[1,1],[2,1],[3,1],[4,1],[5,1],[6,1]] },
            // Face
            { color: '#d4a574', coords: [[2,2],[3,2],[4,2],[5,2],[2,3],[3,3],[4,3],[5,3],[2,4],[3,4],[4,4],[5,4]] },
            // Eyes
            { color: '#1a1a1a', coords: [[3,3],[5,3]] },
            // Mouth (smile)
            { color: '#c4785a', coords: [[3,4],[4,4]] },
            // Jacket (warm brown)
            { color: '#8d6e63', coords: [[1,5],[2,5],[3,5],[4,5],[5,5],[6,5],[0,6],[1,6],[2,6],[3,6],[4,6],[5,6],[6,6],[7,6],[0,7],[1,7],[2,7],[3,7],[4,7],[5,7],[6,7],[7,7],[1,8],[2,8],[5,8],[6,8]] },
            // Clipboard
            { color: '#f5f5dc', coords: [[6,8],[7,8],[7,7]] },
            // Shirt
            { color: '#fff', coords: [[3,5],[4,5],[3,6],[4,6]] },
            // Hands
            { color: '#d4a574', coords: [[0,8],[7,9]] },
            // Pants
            { color: '#37474f', coords: [[2,9],[3,9],[4,9],[5,9],[2,10],[3,10],[4,10],[5,10]] },
            // Shoes
            { color: '#5d4037', coords: [[1,11],[2,11],[3,11],[4,11],[5,11],[6,11]] },
        ]
    },
    {
        id: 'researcher',
        name: 'RESEARCHER',
        role: 'Fact Finder',
        pixels: [
            // Hair (red/auburn)
            { color: '#b33a2d', coords: [[2,0],[3,0],[4,0],[5,0],[1,1],[2,1],[3,1],[4,1],[5,1],[6,1],[1,2],[6,2]] },
            // Face
            { color: '#fdd9b5', coords: [[2,2],[3,2],[4,2],[5,2],[2,3],[3,3],[4,3],[5,3],[2,4],[3,4],[4,4],[5,4]] },
            // Glasses (round)
            { color: '#4fc3f7', coords: [[1,3],[6,3]] },
            // Eyes
            { color: '#1a1a1a', coords: [[3,3],[5,3]] },
            // Mouth
            { color: '#c4785a', coords: [[4,4]] },
            // Lab coat (white)
            { color: '#eceff1', coords: [[1,5],[2,5],[3,5],[4,5],[5,5],[6,5],[0,6],[1,6],[2,6],[3,6],[4,6],[5,6],[6,6],[7,6],[0,7],[1,7],[2,7],[3,7],[4,7],[5,7],[6,7],[7,7],[0,8],[1,8],[2,8],[5,8],[6,8],[7,8]] },
            // Shirt underneath
            { color: '#4caf50', coords: [[3,5],[4,5]] },
            // Magnifying glass
            { color: '#ffd54f', coords: [[7,5],[7,4]] },
            { color: '#81d4fa', coords: [[7,3]] },
            // Hands
            { color: '#fdd9b5', coords: [[0,9],[7,9]] },
            // Pants
            { color: '#455a64', coords: [[2,9],[3,9],[4,9],[5,9],[2,10],[3,10],[4,10],[5,10]] },
            // Shoes
            { color: '#795548', coords: [[1,11],[2,11],[3,11],[4,11],[5,11],[6,11]] },
        ]
    },
    {
        id: 'director',
        name: 'DIRECTOR',
        role: 'Creative Visionary',
        // Pixel art: creative woman with beret and flowing hair
        pixels: [
            // Beret
            { color: '#880e4f', coords: [[1,0],[2,0],[3,0],[4,0],[5,0],[6,0],[2,-1],[3,-1],[4,-1]] },
            // Hair (dark, longer — flows past face)
            { color: '#1a1a1a', coords: [[1,1],[2,1],[3,1],[4,1],[5,1],[6,1],[0,2],[7,2],[0,3],[7,3],[0,4],[7,4],[0,5],[7,5],[0,6],[7,6]] },
            // Face
            { color: '#e8b88a', coords: [[2,2],[3,2],[4,2],[5,2],[2,3],[3,3],[4,3],[5,3],[2,4],[3,4],[4,4],[5,4]] },
            // Sunglasses (stylish, slightly wider)
            { color: '#111', coords: [[2,3],[3,3],[5,3],[6,3]] },
            // Lips
            { color: '#c4505a', coords: [[3,4],[4,4]] },
            // Turtleneck (black)
            { color: '#212121', coords: [[1,5],[2,5],[3,5],[4,5],[5,5],[6,5],[1,6],[2,6],[3,6],[4,6],[5,6],[6,6],[1,7],[2,7],[3,7],[4,7],[5,7],[6,7],[1,8],[2,8],[5,8],[6,8]] },
            // Scarf accent (red)
            { color: '#e94560', coords: [[3,5],[4,5],[3,6],[4,6]] },
            // Hands
            { color: '#e8b88a', coords: [[0,8],[7,8]] },
            // Slim trousers
            { color: '#1a1a1a', coords: [[2,9],[3,9],[4,9],[5,9],[2,10],[3,10],[4,10],[5,10]] },
            // Boots (stylish)
            { color: '#4e342e', coords: [[1,11],[2,11],[3,11],[4,11],[5,11],[6,11]] },
        ]
    },
    {
        id: 'production_manager',
        name: 'PROD. MANAGER',
        role: 'Logistics & Budget',
        pixels: [
            // Hard hat
            { color: '#ffc107', coords: [[1,0],[2,0],[3,0],[4,0],[5,0],[6,0],[0,0],[7,0],[2,-1],[3,-1],[4,-1],[5,-1]] },
            // Hair
            { color: '#5d4037', coords: [[2,1],[3,1],[4,1],[5,1]] },
            // Face
            { color: '#c9956b', coords: [[2,2],[3,2],[4,2],[5,2],[2,3],[3,3],[4,3],[5,3],[2,4],[3,4],[4,4],[5,4]] },
            // Eyes
            { color: '#1a1a1a', coords: [[3,3],[5,3]] },
            // Smile
            { color: '#a0604a', coords: [[3,4],[4,4],[5,4]] },
            // Hi-vis vest
            { color: '#ff9800', coords: [[1,5],[2,5],[5,5],[6,5],[0,6],[1,6],[6,6],[7,6],[0,7],[1,7],[6,7],[7,7]] },
            // Vest stripes
            { color: '#ffeb3b', coords: [[2,6],[5,6],[2,7],[5,7]] },
            // Shirt (dark)
            { color: '#37474f', coords: [[3,5],[4,5],[2,5],[3,6],[4,6],[3,7],[4,7],[1,8],[2,8],[5,8],[6,8]] },
            // Calculator
            { color: '#90a4ae', coords: [[7,7],[7,8]] },
            { color: '#4caf50', coords: [[7,6]] },
            // Hands
            { color: '#c9956b', coords: [[0,8],[7,9]] },
            // Pants (work)
            { color: '#455a64', coords: [[2,9],[3,9],[4,9],[5,9],[2,10],[3,10],[4,10],[5,10]] },
            // Boots
            { color: '#3e2723', coords: [[1,11],[2,11],[3,11],[4,11],[5,11],[6,11]] },
        ]
    }
];
