/**
 * Projekt 04, Task a: MVC Pattern - Model Package
 * 
 * This class is part of the MODEL layer in the Model-View-Controller pattern.
 * The model package contains all game logic and data structures:
 * - Board: The game board with ball positions and game rules
 * - Ball, Cell: Basic game elements
 * - Color, Direction, Role, Winner: Enums for game state
 * - ObservableBoard, BoardObserver: Observer pattern for GUI updates
 * - Exceptions: NotInRangeException, NotYourBallException, OutOfGameException
 * 
 * The model is independent of the user interface and can be used with
 * different view implementations (console, GUI, etc.).
 */
package tuc.isse.projekt01.model;

/**
 * The game field containing 7x7 cells.
 * Place the balls in starting pattern as per the game.
 * Looping through every cell and print the whole board.
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @author xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 * @version 1.0
 */
import java.util.List;
import java.util.ArrayList;
import java.util.EnumSet;

public class Board {

    // Task a: Use Collections instead of Arrays
    // Changed from Cell[][] to List<List<Cell>>
    private List<List<Cell>> grid;
    private final int SIZE = 7;
    
    // Task b: Use EnumSet to group directions
    // Group horizontal movements (LEFT and RIGHT)
    private static final EnumSet<Direction> HORIZONTAL =
            EnumSet.of(Direction.LEFT, Direction.RIGHT);

    // Group vertical movements (UP and DOWN)
    private static final EnumSet<Direction> VERTICAL =
            EnumSet.of(Direction.UP, Direction.DOWN);
    
    // Task e: The Board must have the winner attribute
    private Winner winner;
    
    /**
     * Get the current winner of the game
     * @return Winner.WHITE, Winner.BLACK, or Winner.NONE if game is still ongoing
     */
    public Winner getWinner() {
        return winner;
    }

    /**
     * Constructor - Initializes the game board
     * Task a: Uses Collections (ArrayList) instead of arrays
     */
    public Board() {
        // Task a: Initialize grid using ArrayList instead of arrays
        // Creates List<List<Cell>> structure for 7x7 board
        grid = new ArrayList<>();
        for (int y = 0; y < SIZE; y++) {
            List<Cell> row = new ArrayList<>();  // Each row is also an ArrayList
            for (int x = 0; x < SIZE; x++) {
                row.add(new Cell());
            }
            grid.add(row);
        }
    	
        this.winner = Winner.NONE; // Initially, nobody has won

        // Setup starting positions of balls
        initPositions();
    }
    
    /**
     * Table 07 task a: new methods
     * Number of balls in the row
     * @param row Row index to count balls in
     */
    private int countBallsInRow(int row) {
        int count = 0;
        for (int c = 0; c < SIZE; c++) {
            if (grid.get(row).get(c).getBall() != null) {  // Check if a ball exists in this cell
                count++;
            }
        }
        return count;
    }
    /**
     * Number of balls in the column
     * @param col Column index to count balls in
     */
    private int countBallsInColumn(int col) {
        int count = 0;
        for (int r = 0; r < SIZE; r++) {
            if (grid.get(r).get(col).getBall() != null) {
                count++;
            }
        }
        return count;
    }
    /**
     * Move left or right
     * @param d Direction to calculate horizontal movement for
     */
    private int dx(Direction d) {
        if (d == Direction.LEFT) return -1; // e.g. Move left decreases column index
        if (d == Direction.RIGHT) return 1;
        return 0;
    }
    /**
     * Move up or down
     * @param d Direction to calculate vertical movement for
     */
    private int dy(Direction d) {
        if (d == Direction.UP) return -1; // e.g. Move up decreases row index
        if (d == Direction.DOWN) return 1;
        return 0;
    }

    /**
     * Important: count empty cells strictly between (c1,r1) and (c2,r2) on same line
     * @param c1 Starting column coordinate
     * @param r1 Starting row coordinate
     * @param c2 Ending column coordinate
     * @param r2 Ending row coordinate
     * @param dir Direction of movement
     */
    private int countEmptyCellsBetween(int c1, int r1, int c2, int r2, Direction dir) {
        int dc = dx(dir);
        int dr = dy(dir);

        int c = c1 + dc;
        int r = r1 + dr;
        int empty = 0;

        while (c != c2 || r != r2) {
            if (grid.get(r).get(c).getBall() == null) {
                empty++;
            }
            c += dc;
            r += dr;
        }
        return empty;
    }




    /**
     * Places the balls according to the PDF diagram.
     * White: Top-Left corner area.
     * Black: Bottom-Right corner area.
     */
    private void initPositions() {
        // --- WHITE TEAM ---
        // Top-Left: King at (0,0)
    	grid.get(0).get(0).setBall(new Ball(Color.WHITE, Role.KING));
        // Row 0: 3 Residents to the right
    	grid.get(0).get(1).setBall(new Ball(Color.WHITE, Role.RESIDENT));
    	grid.get(0).get(2).setBall(new Ball(Color.WHITE, Role.RESIDENT));
    	grid.get(0).get(3).setBall(new Ball(Color.WHITE, Role.RESIDENT));
        // Vertical Residents (Column 0)
    	grid.get(1).get(0).setBall(new Ball(Color.WHITE, Role.RESIDENT));
    	grid.get(2).get(0).setBall(new Ball(Color.WHITE, Role.RESIDENT));
    	grid.get(3).get(0).setBall(new Ball(Color.WHITE, Role.RESIDENT));

        // --- BLACK TEAM ---
        // Bottom-Right: King at (6,6)
    	grid.get(6).get(6).setBall(new Ball(Color.BLACK, Role.KING));
        // Row 6: 3 Residents to the left
    	grid.get(6).get(5).setBall(new Ball(Color.BLACK, Role.RESIDENT));
    	grid.get(6).get(4).setBall(new Ball(Color.BLACK, Role.RESIDENT));
    	grid.get(6).get(3).setBall(new Ball(Color.BLACK, Role.RESIDENT));
        // Vertical Residents (Column 6)
    	grid.get(5).get(6).setBall(new Ball(Color.BLACK, Role.RESIDENT));
    	grid.get(4).get(6).setBall(new Ball(Color.BLACK, Role.RESIDENT));
    	grid.get(3).get(6).setBall(new Ball(Color.BLACK, Role.RESIDENT));
    }

    /**
     * Task f: Print the whole board
     * We loop through rows and columns and build a big string.
     */
    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder();

        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                // Get the cell's string representation: "[ ]" or "[B]"
                sb.append(grid.get(y).get(x).toString());
            }
            // After every row, add a new line
            sb.append("\n");
        }
        return sb.toString();
    }
    
    /**
     * Task g helper method:
     * Checks whether a ball can move one step in the given direction
     * without leaving the board.
     * @param columnIndex Column position of the ball
     * @param rowIndex Row position of the ball
     * @param direction Direction to check for valid movement
     */
    public boolean canMove(int columnIndex, int rowIndex, Direction direction) {

        switch (direction) {
            case UP:
                return rowIndex - 1 >= 0;
            case DOWN:
                return rowIndex + 1 < SIZE;
            case LEFT:
                return columnIndex - 1 >= 0;
            case RIGHT:
                return columnIndex + 1 < SIZE;
            default:
                return false;
        }
    }
    
    /**
     * Table 06 Task g:
     * Checks whether a move is valid.
     * The actual movement is NOT implemented yet.
     * 
     * @param color The color of the player making the move
     * @param columnIndex Column position of the ball to move
     * @param rowIndex Row position of the ball to move
     * @param direction Direction to move the ball in
     * @throws NotYourBallException If the ball doesn't belong to the player
     * @throws OutOfGameException If the move would push a ball out of bounds
     * @throws NotInRangeException If the position is outside the board
     */
    // Table 07 Task a: extend moveBall
    public void moveBall(Color color, int columnIndex, int rowIndex, Direction direction)
            throws NotYourBallException, OutOfGameException, NotInRangeException {
    	// Checks for the exceptions at the beginning
        // Check board range
        if (rowIndex < 0 || rowIndex >= SIZE || columnIndex < 0 || columnIndex >= SIZE) {
            throw new NotInRangeException();
        }

        // Check if there is a ball and if it belongs to the player
        Cell startCell = grid.get(rowIndex).get(columnIndex);
        Ball ball = startCell.getBall();

        if (ball == null || ball.getColor() != color) {
            throw new NotYourBallException();
        }

        // Check if the ball would leave the board
        if (!canMove(columnIndex, rowIndex, direction)) {
            throw new OutOfGameException();
        }
        
        // Calculate move distance based on direction
        int steps;
        
        // Task b: Use EnumSet to group directions
        // Determine if movement is vertical or horizontal using EnumSet.contains()
        if (VERTICAL.contains(direction)) {
            // Vertical movement (UP or DOWN): count balls in the row
            steps = countBallsInRow(rowIndex);
        } else if (HORIZONTAL.contains(direction)) {
            // Horizontal movement (LEFT or RIGHT): count balls in the column
            steps = countBallsInColumn(columnIndex);
        } else {
            throw new IllegalArgumentException("Invalid direction");
        }
        
        // Collect all other balls that may also need to move,
        // depending on their position and move distance
        
        int dc = dx(direction);
        int dr = dy(direction);
        
        // Task a: Use ArrayList to collect cells instead of arrays
        // Collect all balls in the direction of movement
        List<Cell> line = new ArrayList<>();
        int c = columnIndex;
        int r = rowIndex;
        while (c >= 0 && c < SIZE && r >= 0 && r < SIZE) {
            Cell current = grid.get(r).get(c);
            if (current.getBall() != null) {
                line.add(current);
            }
            c += dc;
            r += dr;
        }
        
        // Task a: Use ArrayLists to track balls and their destinations
        // Based on the number of empty cells between each ball and the selected ball,
        // determine which balls are pushed
        List<Ball> movingBalls = new ArrayList<>();    // Balls that will move
        List<Cell> targetCells = new ArrayList<>();    // Their destination cells

        boolean opponentKingFallsOff = false;

        for (Cell currentCell : line) {
        	
        	Ball b = currentCell.getBall();
            
            int curCol = -1;
            int curRow = -1;
            // Find its coordinates
            for (int y = 0; y < SIZE; y++) {
                for (int x = 0; x < SIZE; x++) {
                    if (grid.get(y).get(x) == currentCell) {
                        curCol = x;
                        curRow = y;
                    }
                }
            }
            
            // Logic for the selected ball: moves full steps
            if (currentCell == startCell) {
                int newCol = curCol + steps * dc;
                int newRow = curRow + steps * dr;

                if (newCol < 0 || newCol >= SIZE || newRow < 0 || newRow >= SIZE) {
                    throw new OutOfGameException();
                }

                movingBalls.add(b);
                targetCells.add(grid.get(newRow).get(newCol));
                continue;
            }

            // Logics for the balls that be pushed
            // Number of empty cells
            int emptyCells = countEmptyCellsBetween(
                    columnIndex,
                    rowIndex,
                    curCol,
                    curRow,
                    direction
            );

            // Whether it will be pushed
            if (emptyCells > steps) {
                continue; // still
            }

            int moveBy = steps - emptyCells; // the most important rule

            for (int s = 1; s <= moveBy; s++) {
                curCol += dc;
                curRow += dr;

                // step-by-step out of board check
                if (curCol < 0 || curCol >= SIZE || curRow < 0 || curRow >= SIZE) {

//                    if (b.getColor() == color) {
//                        throw new OutOfGameException(); // Fixed: Own balls could also be pushed out of game
//                    }

                    if (b.getRole() == Role.KING) {
                        opponentKingFallsOff = true;    // opponent KING: win
                    }

                    // ball is gone, stop checking this one
                    curCol = Integer.MIN_VALUE;
                    curRow = Integer.MIN_VALUE;
                    break;
                }
            }

            // if ball survived all steps, record final position
            if (curCol != Integer.MIN_VALUE) {
            	movingBalls.add(b);
            	targetCells.add(grid.get(curRow).get(curCol));
            }
        }
        
        // Execute movement
        // Remove the selected ball and other balls that are pushed
        for (Ball b : movingBalls) {
            for (int row = 0; row < SIZE; row++) {
                for (int col = 0; col < SIZE; col++) {
                    if (grid.get(row).get(col).getBall() == b) {
                        grid.get(row).get(col).setBall(null);
                    }
                }
            }
        }

        for (int i = 0; i < movingBalls.size(); i++) {
            targetCells.get(i).setBall(movingBalls.get(i));
        }

        // Table 07 task b: check for a winner
        // One possibility: ball b is opponent King, and it falls off the board
        // Notice: check if King falls off step by step
        if (opponentKingFallsOff) {
            this.winner = (color == Color.WHITE) ? Winner.WHITE : Winner.BLACK;
            return;
        }
        // Another possibility: when the movement complete, check center field (3,3) for KING
        Cell center = grid.get(3).get(3);
        if (center.getBall() != null && center.getBall().getRole() == Role.KING) {
            Color kingColor = center.getBall().getColor();
            this.winner = (kingColor == Color.WHITE) ? Winner.WHITE : Winner.BLACK;
        }

    }
    /**
     * Helper for Task d: Clears the board to set up specific test scenarios.
     * This allows us to test "Winning" without playing a full game.
     */
    public void clearBoard() {
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
            	grid.get(y).get(x).setBall(null);
            }
        }
    }

    /**
     * Helper for Task d: Places a ball manually for testing.
     * @param col Column index (0-6)
     * @param row Row index (0-6)
     * @param ball The ball to place
     */
    public void setBallAt(int col, int row, Ball ball) {
        if (col >= 0 && col < SIZE && row >= 0 && row < SIZE) {
        	grid.get(row).get(col).setBall(ball);
        }
    }
    /**
     * Helper for Tests: Returns the ball at a specific position.
     * Use this instead of accessing 'grid' directly.
     * @param col Column index (0-6)
     * @param row Row index (0-6)
     */
    public Ball getBall(int col, int row) {
        if (col >= 0 && col < SIZE && row >= 0 && row < SIZE) {
            return grid.get(row).get(col).getBall();
        }
        return null;
    }
    
    // =========================================================================
    // PROJEKT 06 (BONUS), TASK A: SAVE AND LOAD FUNCTIONALITY (20 POINTS)
    // =========================================================================
    
    /**
     * Saves the current board state to a file.
     * 
     * TASK: Project 6, Task a - Save Method
     * 
     * This method writes the complete game state to a file, including:
     * - All ball positions (column, row)
     * - Ball colors (WHITE or BLACK)
     * - Ball roles (KING or RESIDENT)
     * - Current winner status
     * 
     * FILE FORMAT:
     * Line 1: Winner status (NONE, WHITE, or BLACK)
     * Lines 2+: For each ball - "col,row,color,role" (one per line)
     * Example:
     *   NONE
     *   0,0,WHITE,KING
     *   1,0,WHITE,RESIDENT
     *   6,6,BLACK,KING
     * 
     * WHY THIS FORMAT:
     * - Simple text format (human-readable for debugging)
     * - Easy to parse when loading
     * - One line per ball makes it extensible
     * - Comma-separated values are standard
     * 
     * PURPOSE:
     * Allows players to save their game progress and return to it later.
     * Essential for any serious game application. Also useful for:
     * - Testing specific board configurations
     * - Debugging game scenarios
     * - Sharing interesting game states
     * 
     * @param path The file path where the board state will be saved.
     *             Can be absolute or relative path. File will be created
     *             if it doesn't exist, overwritten if it does.
     * 
     * @throws IOException if file cannot be written (e.g., permission denied,
     *                     disk full, invalid path)
     * 
     * WHY THROWS IOException:
     * File operations can fail for many reasons outside our control.
     * Throwing IOException lets the caller decide how to handle the error
     * (show message to user, retry, etc.)
     * 
     * USAGE EXAMPLE:
     *   board.save("my_game.txt");
     *   // Later: board.load("my_game.txt");
     */
    public void save(String path) throws java.io.IOException {
        // Use try-with-resources to automatically close file
        // This ensures the file is closed even if an error occurs
        try (java.io.PrintWriter writer = new java.io.PrintWriter(
                new java.io.FileWriter(path))) {
            
            // Line 1: Save winner status
            // WHY FIRST: Winner affects game state, should be loaded first
            writer.println(winner.toString());
            
            // Lines 2+: Save each ball's information
            // Scan entire grid for balls
            for (int row = 0; row < SIZE; row++) {
                for (int col = 0; col < SIZE; col++) {
                    Ball ball = getBall(col, row);
                    
                    // Only save cells that contain balls
                    if (ball != null) {
                        // Format: col,row,color,role
                        // WHY THIS ORDER: Column first matches (x,y) convention
                        // WHY COMMAS: Standard CSV format, easy to parse
                        writer.printf("%d,%d,%s,%s%n",
                                    col, row,
                                    ball.getColor().toString(),
                                    ball.getRole().toString());
                    }
                }
            }
            
            // File automatically closed by try-with-resources
            // Flush happens automatically on close
        }
        // If IOException occurs, it propagates to caller
    }
    
    /**
     * Loads a board state from a file.
     * 
     * TASK: Project 6, Task a - Load Method
     * 
     * This method reads a previously saved game state from a file and
     * restores the board to that state. It reads the file created by
     * save() and reconstructs all ball positions and game state.
     * 
     * IMPORTANT: This method does NOT automatically clear the board first.
     * The caller should call clearBoard() before load() if starting fresh,
     * or call load() on a new Board() which starts empty.
     * 
     * ALGORITHM:
     * 1. Read winner status from first line
     * 2. Read each subsequent line containing ball data
     * 3. Parse the comma-separated values
     * 4. Create Ball objects with the specified properties
     * 5. Place balls at the saved positions
     * 
     * WHY THIS APPROACH:
     * - Mirrors the save() format exactly
     * - Simple line-by-line reading is reliable
     * - Error checking ensures file format is valid
     * 
     * PURPOSE:
     * Restores a previously saved game, allowing players to:
     * - Continue games from where they left off
     * - Share game scenarios with others
     * - Test specific board configurations
     * 
     * @param path The file path to load the board state from.
     *             File must exist and be in the correct format
     *             (created by save() method).
     * 
     * @throws IOException if file cannot be read (e.g., file not found,
     *                     permission denied, corrupted file)
     * @throws IllegalArgumentException if file format is invalid
     * 
     * WHY THESE EXCEPTIONS:
     * - IOException: File system errors (not our fault)
     * - IllegalArgumentException: Invalid data format (corrupted/wrong file)
     * These different exceptions let the caller distinguish between
     * file access problems vs. data format problems.
     * 
     * USAGE EXAMPLE:
     *   Board board = new Board();
     *   board.clearBoard();  // Start with empty board
     *   board.load("my_game.txt");  // Restore saved state
     */
    public void load(String path) throws java.io.IOException {
        // Use try-with-resources for automatic file closing
        try (java.io.BufferedReader reader = new java.io.BufferedReader(
                new java.io.FileReader(path))) {
            
            // Line 1: Read and restore winner status
            String winnerLine = reader.readLine();
            if (winnerLine == null) {
                throw new IllegalArgumentException(
                    "Invalid save file: Empty or missing winner line");
            }
            
            // Parse winner status
            // WHY valueOf: Converts string "WHITE" to Winner.WHITE enum
            try {
                this.winner = Winner.valueOf(winnerLine.trim());
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException(
                    "Invalid save file: Unknown winner value: " + winnerLine);
            }
            
            // Lines 2+: Read and restore each ball
            String line;
            while ((line = reader.readLine()) != null) {
                // Skip empty lines (allows for formatting flexibility)
                if (line.trim().isEmpty()) {
                    continue;
                }
                
                // Parse line: "col,row,color,role"
                String[] parts = line.split(",");
                
                // Validate format: should have exactly 4 parts
                if (parts.length != 4) {
                    throw new IllegalArgumentException(
                        "Invalid save file: Ball line should have 4 values: " 
                        + line);
                }
                
                try {
                    // Parse each component
                    int col = Integer.parseInt(parts[0].trim());
                    int row = Integer.parseInt(parts[1].trim());
                    Color color = Color.valueOf(parts[2].trim());
                    Role role = Role.valueOf(parts[3].trim());
                    
                    // Validate position is within board bounds
                    if (col < 0 || col >= SIZE || row < 0 || row >= SIZE) {
                        throw new IllegalArgumentException(
                            "Invalid save file: Position out of bounds: " 
                            + col + "," + row);
                    }
                    
                    // Create and place the ball
                    Ball ball = new Ball(color, role);
                    setBallAt(col, row, ball);
                    
                } catch (NumberFormatException e) {
                    throw new IllegalArgumentException(
                        "Invalid save file: Invalid number format in line: " 
                        + line);
                } catch (IllegalArgumentException e) {
                    // Catches enum valueOf failures or position validation
                    throw new IllegalArgumentException(
                        "Invalid save file: " + e.getMessage() + " in line: " 
                        + line);
                }
            }
            
            // File automatically closed by try-with-resources
        }
        // IOException propagates to caller if file access fails
    }
}

